"""Context engineering: what an agent may see, and what it actually saw.

Context is a governed, auditable resource rather than whatever was concatenated
into a prompt. A :class:`ContextPolicy` states the rules before selection; a
:class:`ContextBundle` records immutably what was selected and what was not; the
assembler between them is pure. See ADR-0006.

The addendum adds a requirement: an agent executing a DeliveryContract must be
shown the controls it will be judged against. ``require_delivery_context``
enforces that, so an agent cannot be blamed for missing a checklist it was never
given.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from domain.metamodel.base import (
    EntityRef,
    MetamodelEntity,
    MetamodelModel,
    ProvenancedEntity,
    new_ulid,
    utc_now,
)
from domain.metamodel.enums import (
    ContextItemKind,
    DropReason,
    EntityType,
    MemoryScope,
    OverflowStrategy,
    TrustLevel,
    Twin,
)


class Memory(MetamodelEntity):
    """Durable state an agent may carry between runs, scoped explicitly."""

    entity_type: EntityType = EntityType.MEMORY
    twin: Twin = Twin.SHARED

    memory_key: str = Field(min_length=1)
    scope: MemoryScope
    subject_ref: EntityRef | None = None
    content_reference: str = Field(min_length=1)
    trust_level: TrustLevel = TrustLevel.LOW
    retention_days: int | None = Field(default=None, ge=0)
    writeback_policy: str = Field(
        default="explicit", description="never | explicit | automatic"
    )
    last_written_at: datetime | None = None

    @model_validator(mode="after")
    def _wide_scopes_need_retention(self) -> Memory:
        if (
            self.scope in (MemoryScope.PROJECT, MemoryScope.ORGANIZATION)
            and self.writeback_policy == "automatic"
            and self.retention_days is None
        ):
            raise ValueError(
                f"{self.scope.value}-scoped memory with automatic writeback must set "
                "retention_days; unbounded shared memory has no review horizon."
            )
        return self


class ContextPolicy(MetamodelEntity):
    """The rules governing what may enter an agent's context."""

    entity_type: EntityType = EntityType.CONTEXT_POLICY
    twin: Twin = Twin.SHARED

    policy_key: str = Field(min_length=1)

    max_tokens: int = Field(gt=0)
    reserved_tokens: int = Field(default=0, ge=0)

    allowed_kinds: list[ContextItemKind] = Field(
        default_factory=list, description="Empty means all kinds are admissible."
    )
    kind_priorities: dict[ContextItemKind, int] = Field(default_factory=dict)
    max_items_per_kind: dict[ContextItemKind, int] = Field(default_factory=dict)

    minimum_trust: TrustLevel = TrustLevel.LOW
    max_age_days: int | None = Field(default=None, ge=0)
    require_citation: bool = True
    deduplicate: bool = True
    redact_patterns: list[str] = Field(default_factory=list)
    overflow_strategy: OverflowStrategy = OverflowStrategy.DROP_LOWEST_PRIORITY

    #: When true, delivery-control items (checklist, criteria, gate rules) are
    #: exempt from budget eviction. An agent judged against controls it was
    #: never shown is being set up to fail.
    require_delivery_context: bool = Field(
        default=False,
        description="Pin delivery-control items so the budget cannot evict them.",
    )

    @property
    def usable_tokens(self) -> int:
        return max(0, self.max_tokens - self.reserved_tokens)

    @model_validator(mode="after")
    def _reserve_must_fit(self) -> ContextPolicy:
        if self.reserved_tokens >= self.max_tokens:
            raise ValueError(
                f"reserved_tokens ({self.reserved_tokens}) leaves no room within max_tokens "
                f"({self.max_tokens})."
            )
        return self


class ContextItem(ProvenancedEntity):
    """One candidate piece of context, with everything needed to rank it."""

    entity_type: EntityType = EntityType.CONTEXT_ITEM
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    kind: ContextItemKind
    source_ref: EntityRef | None = None
    content_reference: str | None = None
    content: str | None = None
    content_hash: str | None = None
    token_estimate: int = Field(ge=0)
    priority: int = Field(default=0, description="Higher is more important.")
    trust_level: TrustLevel = TrustLevel.MEDIUM
    as_of: datetime = Field(default_factory=utc_now)
    #: Marks an item the policy must not evict -- set for delivery controls when
    #: the policy requires them.
    pinned: bool = False

    @property
    def is_citable(self) -> bool:
        return bool(self.content_reference) or self.source_ref is not None


class DroppedItem(MetamodelModel):
    """A candidate that did not make the bundle, and why."""

    item_id: str
    kind: ContextItemKind
    reason: DropReason
    detail: str | None = None
    token_estimate: int = Field(default=0, ge=0)


class ContextBundle(MetamodelEntity):
    """The immutable result of one context assembly."""

    entity_type: EntityType = EntityType.CONTEXT_BUNDLE
    twin: Twin = Twin.SHARED

    id: str = Field(default_factory=new_ulid, min_length=1, max_length=256)
    policy_ref: EntityRef
    agent_ref: EntityRef | None = None
    task_ref: EntityRef | None = None
    #: The delivery contract this context was assembled for, if any.
    contract_ref: EntityRef | None = None
    assembled_at: datetime = Field(default_factory=utc_now)

    items: list[ContextItem] = Field(default_factory=list)
    dropped: list[DroppedItem] = Field(default_factory=list)

    budget_tokens: int = Field(ge=0)
    tokens_used: int = Field(ge=0)
    bundle_hash: str = Field(min_length=1)

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.budget_tokens - self.tokens_used)

    def manifest(self) -> dict[str, object]:
        """A compact account of what the agent was shown, for the audit record."""
        return {
            "bundle_id": self.id,
            "bundle_hash": self.bundle_hash,
            "policy": str(self.policy_ref),
            "contract": str(self.contract_ref) if self.contract_ref else None,
            "assembled_at": self.assembled_at.isoformat(),
            "budget_tokens": self.budget_tokens,
            "tokens_used": self.tokens_used,
            "tokens_remaining": self.tokens_remaining,
            "included": [
                {
                    "id": item.id,
                    "kind": item.kind.value,
                    "name": item.name,
                    "source": str(item.source_ref) if item.source_ref else item.content_reference,
                    "tokens": item.token_estimate,
                    "trust": item.trust_level.value,
                    "provenance": item.provenance.value,
                    "pinned": item.pinned,
                }
                for item in self.items
            ],
            "excluded": [
                {
                    "id": d.item_id,
                    "kind": d.kind.value,
                    "reason": d.reason.value,
                    "detail": d.detail,
                }
                for d in self.dropped
            ],
        }

    @model_validator(mode="after")
    def _must_respect_budget_and_pin_policy(self) -> ContextBundle:
        if self.tokens_used > self.budget_tokens:
            raise ValueError(
                f"bundle uses {self.tokens_used} tokens against a budget of "
                f"{self.budget_tokens}; the assembler must never overrun the policy."
            )
        if self.policy_ref.version is None:
            raise ValueError(
                "policy_ref must pin a version -- a bundle that cannot name the exact rules "
                "that produced it is not reproducible."
            )
        return self
