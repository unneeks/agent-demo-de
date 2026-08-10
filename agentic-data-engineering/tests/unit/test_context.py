"""Context assembly: determinism, budget, accountability, and delivery awareness.

Context selection is the step that most often explains a wrong answer, so each
guarantee is asserted directly rather than inferred from an end-to-end result.
"""

from __future__ import annotations

import random
from datetime import datetime

import pytest

from domain.metamodel.entities.shared.context import ContextBundle, Memory
from domain.metamodel.enums import (
    ContextItemKind,
    DropReason,
    EntityType,
    MemoryScope,
    OverflowStrategy,
    TrustLevel,
)
from engines.context import (
    ContextOverflowError,
    DeliveryContextError,
    FixedTokenEstimator,
    HeuristicTokenEstimator,
    assemble,
)
from tests.conftest import make_context_item, make_policy


class TestDeterminism:
    def test_input_order_does_not_change_the_bundle(self, fixed_now) -> None:
        policy = make_policy(max_tokens=1000)
        items = [
            make_context_item(f"i{n}", priority=n % 3, tokens=90, now=fixed_now)
            for n in range(10)
        ]
        baseline = assemble(policy, items, now=fixed_now)
        for seed in range(5):
            shuffled = items[:]
            random.Random(seed).shuffle(shuffled)
            assert assemble(policy, shuffled, now=fixed_now).bundle_hash == baseline.bundle_hash

    def test_repeated_assembly_is_stable(self, fixed_now) -> None:
        policy = make_policy(max_tokens=500)
        items = [make_context_item(f"i{n}", tokens=100, now=fixed_now) for n in range(4)]
        assert len({assemble(policy, items, now=fixed_now).bundle_hash for _ in range(10)}) == 1

    def test_content_change_changes_the_hash(self, fixed_now) -> None:
        """Same selection, different content, must not read as 'same context'."""
        policy = make_policy(max_tokens=500)
        original = make_context_item("i1", now=fixed_now, content="the original text")
        edited = original.model_copy(update={"content": "the edited text"})
        assert (
            assemble(policy, [original], now=fixed_now).bundle_hash
            != assemble(policy, [edited], now=fixed_now).bundle_hash
        )

    def test_policy_version_changes_the_hash(self, fixed_now) -> None:
        items = [make_context_item("i1", now=fixed_now)]
        assert (
            assemble(make_policy(version="1.0.0"), items, now=fixed_now).bundle_hash
            != assemble(make_policy(version="1.1.0"), items, now=fixed_now).bundle_hash
        )


class TestBudget:
    def test_never_exceeds_the_usable_budget(self, fixed_now) -> None:
        policy = make_policy(max_tokens=500, reserved_tokens=100)
        items = [make_context_item(f"i{n}", tokens=150, now=fixed_now) for n in range(10)]
        bundle = assemble(policy, items, now=fixed_now)
        assert bundle.budget_tokens == 400
        assert bundle.tokens_used <= 400

    def test_reservation_cannot_consume_the_whole_budget(self) -> None:
        with pytest.raises(ValueError, match="leaves no room"):
            make_policy(max_tokens=100, reserved_tokens=100)

    def test_highest_priority_survives_the_squeeze(self, fixed_now) -> None:
        policy = make_policy(max_tokens=200)
        bundle = assemble(
            policy,
            [
                make_context_item("low", priority=1, tokens=150, now=fixed_now),
                make_context_item("high", priority=9, tokens=150, now=fixed_now),
            ],
            now=fixed_now,
        )
        assert [i.id for i in bundle.items] == ["high"]

    def test_fail_strategy_raises_rather_than_shrinking(self, fixed_now) -> None:
        policy = make_policy(max_tokens=100, overflow_strategy=OverflowStrategy.FAIL)
        items = [make_context_item(f"i{n}", tokens=80, now=fixed_now) for n in range(3)]
        with pytest.raises(ContextOverflowError, match="overflow_strategy is FAIL"):
            assemble(policy, items, now=fixed_now)

    def test_bundle_rejects_an_overrun_it_did_not_produce(self, fixed_now) -> None:
        policy = make_policy(max_tokens=100)
        bundle = assemble(policy, [make_context_item("i1", tokens=50, now=fixed_now)])
        with pytest.raises(ValueError, match="never overrun the policy"):
            ContextBundle(**{**bundle.model_dump(), "tokens_used": 999})


class TestAccountability:
    def _candidates(self, now):
        return [
            make_context_item("kept", priority=9, tokens=100, now=now),
            make_context_item("crowded-out", priority=1, tokens=150, now=now),
            make_context_item("untrusted", trust=TrustLevel.UNTRUSTED, now=now),
            make_context_item("stale", age_days=90, now=now),
            make_context_item("uncitable", citable=False, now=now),
        ]

    def _policy(self):
        return make_policy(
            max_tokens=200,
            minimum_trust=TrustLevel.MEDIUM,
            max_age_days=30,
            require_citation=True,
        )

    def test_every_candidate_is_included_or_explained(self, fixed_now) -> None:
        candidates = self._candidates(fixed_now)
        bundle = assemble(self._policy(), candidates, now=fixed_now)
        accounted = {i.id for i in bundle.items} | {d.item_id for d in bundle.dropped}
        assert accounted == {c.id for c in candidates}

    @pytest.mark.parametrize(
        ("item_id", "expected"),
        [
            ("untrusted", DropReason.BELOW_TRUST_FLOOR),
            ("stale", DropReason.STALE),
            ("uncitable", DropReason.MISSING_CITATION),
            ("crowded-out", DropReason.BUDGET_EXCEEDED),
        ],
    )
    def test_each_exclusion_carries_the_right_reason(self, fixed_now, item_id, expected) -> None:
        bundle = assemble(self._policy(), self._candidates(fixed_now), now=fixed_now)
        reasons = {d.item_id: d.reason for d in bundle.dropped}
        assert reasons[item_id] is expected

    def test_filters_run_before_ranking(self, fixed_now) -> None:
        """A top-priority untrusted item reads as untrusted, not as crowded out."""
        policy = make_policy(max_tokens=10_000, minimum_trust=TrustLevel.HIGH)
        bundle = assemble(
            policy,
            [make_context_item("vip", priority=99, trust=TrustLevel.LOW, now=fixed_now)],
            now=fixed_now,
        )
        assert bundle.dropped[0].reason is DropReason.BELOW_TRUST_FLOOR

    def test_manifest_reports_both_sides(self, fixed_now) -> None:
        bundle = assemble(
            make_policy(max_tokens=100),
            [
                make_context_item("in", priority=9, tokens=50, now=fixed_now),
                make_context_item("out", priority=1, tokens=500, now=fixed_now),
            ],
            now=fixed_now,
        )
        manifest = bundle.manifest()
        assert [i["id"] for i in manifest["included"]] == ["in"]
        assert [e["id"] for e in manifest["excluded"]] == ["out"]

    def test_duplicate_content_is_dropped_once(self, fixed_now) -> None:
        bundle = assemble(
            make_policy(max_tokens=10_000),
            [
                make_context_item("first", content="identical", now=fixed_now),
                make_context_item("second", content="identical", now=fixed_now),
            ],
            now=fixed_now,
        )
        assert len(bundle.items) == 1
        assert bundle.dropped[0].reason is DropReason.DUPLICATE


class TestDeliveryAwareness:
    """An agent must see the controls it will be judged against."""

    def test_delivery_controls_are_pinned_against_the_budget(self, fixed_now) -> None:
        policy = make_policy(max_tokens=300, require_delivery_context=True)
        bundle = assemble(
            policy,
            [
                make_context_item("code1", kind=ContextItemKind.CODE, priority=9, tokens=150, now=fixed_now),
                make_context_item("code2", kind=ContextItemKind.CODE, priority=9, tokens=150, now=fixed_now),
                make_context_item("checklist", kind=ContextItemKind.CHECKLIST, priority=0, tokens=100, now=fixed_now),
            ],
            now=fixed_now,
        )
        included = [i.id for i in bundle.items]
        assert "checklist" in included, "a pinned control must not be evicted by the budget"
        assert bundle.items[0].id == "checklist", "pinned items rank first"

    def test_unpinned_policy_lets_the_control_be_evicted(self, fixed_now) -> None:
        """Contrast case: without the flag, priority alone decides."""
        policy = make_policy(max_tokens=300, require_delivery_context=False)
        bundle = assemble(
            policy,
            [
                make_context_item("code1", kind=ContextItemKind.CODE, priority=9, tokens=150, now=fixed_now),
                make_context_item("code2", kind=ContextItemKind.CODE, priority=9, tokens=150, now=fixed_now),
                make_context_item("checklist", kind=ContextItemKind.CHECKLIST, priority=0, tokens=100, now=fixed_now),
            ],
            now=fixed_now,
        )
        assert "checklist" not in [i.id for i in bundle.items]

    def test_unfittable_controls_raise_rather_than_drop(self, fixed_now) -> None:
        """Judging an agent on controls it was never shown is worse than not running."""
        policy = make_policy(max_tokens=50, require_delivery_context=True)
        with pytest.raises(DeliveryContextError, match="never shown"):
            assemble(
                policy,
                [make_context_item("checklist", kind=ContextItemKind.CHECKLIST, tokens=200, now=fixed_now)],
                now=fixed_now,
            )

    def test_per_kind_caps_do_not_evict_pinned_controls(self, fixed_now) -> None:
        policy = make_policy(
            max_tokens=10_000,
            require_delivery_context=True,
            max_items_per_kind={ContextItemKind.CHECKLIST: 1},
        )
        bundle = assemble(
            policy,
            [
                make_context_item(f"cl{n}", kind=ContextItemKind.CHECKLIST, tokens=10, now=fixed_now)
                for n in range(3)
            ],
            now=fixed_now,
        )
        assert len(bundle.items) == 3

    def test_bundle_records_the_contract_it_served(self, fixed_now) -> None:
        from tests.conftest import ref

        bundle = assemble(
            make_policy(max_tokens=500),
            [make_context_item("i1", tokens=50, now=fixed_now)],
            contract_ref=ref(EntityType.DELIVERY_CONTRACT, "contract.logical-data-model"),
            now=fixed_now,
        )
        assert bundle.manifest()["contract"] is not None


class TestPolicyControls:
    def test_disallowed_kinds_never_enter(self, fixed_now) -> None:
        policy = make_policy(max_tokens=10_000, allowed_kinds=[ContextItemKind.POLICY])
        bundle = assemble(
            policy,
            [
                make_context_item("p", kind=ContextItemKind.POLICY, now=fixed_now),
                make_context_item("c", kind=ContextItemKind.CODE, now=fixed_now),
            ],
            now=fixed_now,
        )
        assert [i.id for i in bundle.items] == ["p"]

    def test_redaction_removes_matches_before_assembly(self, fixed_now) -> None:
        policy = make_policy(max_tokens=10_000, redact_patterns=[r"sk-[a-z0-9]+"])
        bundle = assemble(
            policy,
            [make_context_item("secret", content="token sk-abc123 here", now=fixed_now)],
            now=fixed_now,
        )
        assert "sk-abc123" not in (bundle.items[0].content or "")

    def test_policy_reference_is_version_pinned(self, fixed_now) -> None:
        assert assemble(make_policy(version="2.3.0"), [], now=fixed_now).policy_ref.version == "2.3.0"


class TestTokenEstimation:
    def test_heuristic_is_monotonic_and_deterministic(self) -> None:
        estimator = HeuristicTokenEstimator()
        assert estimator.estimate("") == 0
        assert estimator.estimate("a") <= estimator.estimate("a much longer piece of text")
        assert len({estimator.estimate("select * from t") for _ in range(20)}) == 1

    def test_estimator_is_swappable(self, fixed_now) -> None:
        policy = make_policy(max_tokens=250)
        items = [make_context_item(f"i{n}", content=f"text {n}", now=fixed_now) for n in range(4)]
        bundle = assemble(policy, items, estimator=FixedTokenEstimator(100), now=fixed_now)
        assert bundle.tokens_used == 200 and len(bundle.items) == 2


class TestMemoryScopes:
    def test_shared_automatic_memory_needs_a_retention_horizon(self) -> None:
        with pytest.raises(ValueError, match="must set retention_days"):
            Memory(
                id="m1",
                name="shared",
                entity_type=EntityType.MEMORY,
                memory_key="shared",
                scope=MemoryScope.ORGANIZATION,
                content_reference="memory://shared",
                writeback_policy="automatic",
            )

    def test_run_scoped_memory_needs_no_retention(self) -> None:
        memory = Memory(
            id="m2",
            name="run",
            entity_type=EntityType.MEMORY,
            memory_key="run",
            scope=MemoryScope.RUN,
            content_reference="memory://run",
            writeback_policy="automatic",
        )
        assert memory.scope is MemoryScope.RUN
