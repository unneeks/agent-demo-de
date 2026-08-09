"""Deterministic context assembly.

Given a policy and a pool of candidates, produce the context an agent will
actually see -- and a full account of what was excluded and why. Pure and
LLM-free, because context selection is the step that most often explains a wrong
answer and must therefore be inspectable on its own.

Guarantees, each covered by a test:

1. **Deterministic.** Same policy version and candidates in any order produce
   byte-identical bundles, including ``bundle_hash``.
2. **Budget-respecting.** ``tokens_used`` never exceeds the usable budget.
3. **Accountable.** Every candidate is either in ``items`` or in ``dropped``
   with a reason.
4. **Citable.** With ``require_citation``, nothing enters that the agent could
   not later cite.

Plus one the addendum adds:

5. **Delivery-aware.** With ``require_delivery_context``, the controls an agent
   will be judged against cannot be evicted by the budget. An agent blamed for
   missing a checklist it was never shown is being set up to fail.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta

from domain.metamodel.base import EntityRef, utc_now
from domain.metamodel.entities.shared.context import (
    ContextBundle,
    ContextItem,
    ContextPolicy,
    DroppedItem,
)
from domain.metamodel.enums import (
    DELIVERY_CONTEXT_KINDS,
    TRUST_ORDER,
    DropReason,
    OverflowStrategy,
)
from engines.context.budget import DEFAULT_ESTIMATOR, TokenEstimator


class ContextOverflowError(Exception):
    """Candidates exceeded the budget under an ``OverflowStrategy.FAIL`` policy."""


class DeliveryContextError(Exception):
    """Mandatory delivery controls could not fit within the policy budget.

    Raised rather than silently dropping them: an agent judged against controls
    it was never shown is worse than an agent that did not run.
    """


def _redact(text: str, patterns: list[str]) -> tuple[str, bool]:
    redacted = text
    for pattern in patterns:
        redacted = re.sub(pattern, "[REDACTED]", redacted)
    return redacted, redacted != text


def _sort_key(item: ContextItem, policy: ContextPolicy) -> tuple[int, int, int, int, float, str]:
    """Total ordering over candidates.

    Every component is an explicit property of the item -- nothing depends on
    input order or dict iteration -- so ranking is reproducible across runs and
    processes. Pinned items sort first; the trailing id breaks ties so two
    otherwise identical items always order the same way.
    """
    kind_priority = policy.kind_priorities.get(item.kind, 0)
    return (
        0 if item.pinned else 1,
        -item.priority,
        -kind_priority,
        -TRUST_ORDER[item.trust_level],
        -item.as_of.timestamp(),
        item.id,
    )


def _compute_bundle_hash(policy: ContextPolicy, items: list[ContextItem], budget: int) -> str:
    """Digest over the policy identity and the ordered item identities.

    Content hashes are included where present, so editing an item's content
    changes the hash even when the selection is unchanged -- otherwise "same
    context" would be a claim about item ids rather than about what was read.
    """
    payload = {
        "policy_id": policy.id,
        "policy_version": policy.version,
        "budget": budget,
        "items": [
            {
                "id": item.id,
                "kind": item.kind.value,
                "tokens": item.token_estimate,
                "content_hash": item.content_hash,
                "source": str(item.source_ref) if item.source_ref else item.content_reference,
            }
            for item in items
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def assemble(  # noqa: C901
    policy: ContextPolicy,
    candidates: list[ContextItem],
    *,
    estimator: TokenEstimator | None = None,
    agent_ref: EntityRef | None = None,
    task_ref: EntityRef | None = None,
    contract_ref: EntityRef | None = None,
    now: datetime | None = None,
    bundle_id: str | None = None,
) -> ContextBundle:
    """Assemble a context bundle from candidates under a policy.

    Admission runs as a sequence of filters -- kind, trust, staleness, citation,
    duplication -- and only then a greedy budget fill over the ranked survivors.
    Filtering before ranking matters: a high-priority item that fails the trust
    floor should be reported as untrusted, not as crowded out.
    """
    estimator = estimator or DEFAULT_ESTIMATOR
    reference_time = now or utc_now()
    dropped: list[DroppedItem] = []
    admitted: list[ContextItem] = []
    seen_hashes: set[str] = set()

    allowed_kinds = set(policy.allowed_kinds) if policy.allowed_kinds else None
    stale_before = (
        reference_time - timedelta(days=policy.max_age_days)
        if policy.max_age_days is not None
        else None
    )
    minimum_trust_rank = TRUST_ORDER[policy.minimum_trust]

    def drop(item: ContextItem, reason: DropReason, detail: str | None = None) -> None:
        dropped.append(
            DroppedItem(
                item_id=item.id,
                kind=item.kind,
                reason=reason,
                detail=detail,
                token_estimate=item.token_estimate,
            )
        )

    # -- admission filters -------------------------------------------------
    for candidate in candidates:
        # A delivery-control item under require_delivery_context is pinned, and
        # pinning survives the ranking and the budget fill.
        item = candidate
        if policy.require_delivery_context and candidate.kind in DELIVERY_CONTEXT_KINDS:
            item = candidate.model_copy(update={"pinned": True})

        if allowed_kinds is not None and item.kind not in allowed_kinds:
            drop(item, DropReason.KIND_NOT_ALLOWED, f"{item.kind.value} not admissible")
            continue

        if TRUST_ORDER[item.trust_level] < minimum_trust_rank:
            drop(
                item,
                DropReason.BELOW_TRUST_FLOOR,
                f"{item.trust_level.value} below {policy.minimum_trust.value}",
            )
            continue

        if stale_before is not None and item.as_of < stale_before:
            drop(
                item,
                DropReason.STALE,
                f"as_of {item.as_of.date()} older than {policy.max_age_days} days",
            )
            continue

        if policy.require_citation and not item.is_citable:
            drop(item, DropReason.MISSING_CITATION, "no source_ref or content_reference to cite")
            continue

        if policy.redact_patterns and item.content:
            cleaned, changed = _redact(item.content, policy.redact_patterns)
            if changed:
                item = item.model_copy(update={"content": cleaned, "content_hash": None})

        # Re-estimate from the (possibly redacted) content so the budget
        # reflects what will really be sent.
        if item.content is not None:
            item = item.model_copy(update={"token_estimate": estimator.estimate(item.content)})

        if policy.deduplicate:
            fingerprint = item.content_hash or hashlib.sha256(
                (item.content or item.content_reference or item.id).encode("utf-8")
            ).hexdigest()
            if fingerprint in seen_hashes:
                drop(item, DropReason.DUPLICATE, "identical content already admitted")
                continue
            seen_hashes.add(fingerprint)

        admitted.append(item)

    admitted.sort(key=lambda i: _sort_key(i, policy))

    # -- per-kind caps -----------------------------------------------------
    if policy.max_items_per_kind:
        kept: list[ContextItem] = []
        counts: dict[str, int] = {}
        for item in admitted:
            cap = policy.max_items_per_kind.get(item.kind)
            count = counts.get(item.kind.value, 0)
            if cap is not None and count >= cap and not item.pinned:
                drop(item, DropReason.KIND_NOT_ALLOWED, f"exceeds cap of {cap} for {item.kind.value}")
                continue
            counts[item.kind.value] = count + 1
            kept.append(item)
        admitted = kept

    # -- budget fill -------------------------------------------------------
    budget = policy.usable_tokens
    total_requested = sum(item.token_estimate for item in admitted)

    if total_requested > budget and policy.overflow_strategy is OverflowStrategy.FAIL:
        raise ContextOverflowError(
            f"candidates need {total_requested} tokens but policy {policy.policy_key!r} "
            f"allows {budget}; overflow_strategy is FAIL"
        )

    pinned_cost = sum(item.token_estimate for item in admitted if item.pinned)
    if pinned_cost > budget:
        raise DeliveryContextError(
            f"policy {policy.policy_key!r} requires delivery context costing {pinned_cost} "
            f"tokens but allows only {budget}. Raise the budget or reduce the controls -- "
            "an agent must not be judged against controls it was never shown."
        )

    selected: list[ContextItem] = []
    used = 0
    for item in admitted:
        if used + item.token_estimate <= budget:
            selected.append(item)
            used += item.token_estimate
            continue

        remaining = budget - used
        if (
            policy.overflow_strategy is OverflowStrategy.TRUNCATE_LOWEST_PRIORITY
            and remaining > 0
            and item.content
            and not item.pinned
        ):
            # Truncate proportionally to the surviving token share, then
            # re-estimate -- the ratio is approximate by construction.
            keep_ratio = remaining / item.token_estimate
            cutoff = max(1, int(len(item.content) * keep_ratio))
            truncated_text = item.content[:cutoff]
            truncated = item.model_copy(
                update={
                    "content": truncated_text,
                    "token_estimate": estimator.estimate(truncated_text),
                    "content_hash": None,
                }
            )
            if truncated.token_estimate <= remaining:
                selected.append(truncated)
                used += truncated.token_estimate
                continue

        drop(
            item,
            DropReason.BUDGET_EXCEEDED,
            f"needs {item.token_estimate}, {budget - used} of {budget} remaining",
        )

    bundle_hash = _compute_bundle_hash(policy, selected, budget)

    return ContextBundle(
        id=bundle_id or f"bundle-{bundle_hash[:16]}",
        name=f"context for {policy.policy_key}",
        entity_type=ContextBundle.model_fields["entity_type"].default,
        policy_ref=EntityRef(type=policy.entity_type, id=policy.id, version=policy.version),
        agent_ref=agent_ref,
        task_ref=task_ref,
        contract_ref=contract_ref,
        assembled_at=reference_time,
        items=selected,
        dropped=sorted(dropped, key=lambda d: (d.reason.value, d.item_id)),
        budget_tokens=budget,
        tokens_used=used,
        bundle_hash=bundle_hash,
    )
