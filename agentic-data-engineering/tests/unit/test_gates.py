"""Checklist evaluation and gate readiness, against the worked delivery model.

These are the tests that decide whether delivery metadata is executable or
decorative. They run against the real registry model rather than toy fixtures,
so a change to the model that breaks the engines is caught here.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.metamodel.entities.delivery import ChecklistItemResult, Waiver
from domain.metamodel.enums import (
    ChecklistItemStatus,
    CompletionRule,
    EntityType,
    GateDimension,
    GateStatus,
)
from engines.gates import (
    GateState,
    assess_gate,
    evaluate_checklist,
    machine_evaluable_share,
    unevaluated_items,
)
from tests.conftest import ref

CHECKLIST = "logical-model-checklist"
GATE = "gate.data-architecture-review"


def _pass_all(items, *, skip: set[str] | None = None) -> list[ChecklistItemResult]:
    """Pass every item, optionally skipping some so they read as PENDING."""
    skip = skip or set()
    return [
        ChecklistItemResult(
            item_key=item.item_key,
            status=ChecklistItemStatus.PASS,
            evidence_refs=[ref(EntityType.EVIDENCE, f"ev-{item.item_key}")]
            if item.evidence_required
            else [],
        )
        for item in items
        if item.item_key not in skip
    ]


class TestChecklistEvaluation:
    def test_all_mandatory_passing_completes(self, delivery_model) -> None:
        checklist = delivery_model.checklists[CHECKLIST]
        items = delivery_model.items_for(CHECKLIST)
        outcome = evaluate_checklist(checklist, items, _pass_all(items))
        assert outcome.complete
        assert not outcome.outstanding

    def test_one_outstanding_mandatory_item_blocks_completion(self, delivery_model) -> None:
        checklist = delivery_model.checklists[CHECKLIST]
        items = delivery_model.items_for(CHECKLIST)
        outcome = evaluate_checklist(checklist, items, _pass_all(items, skip={"LMC-09"}))
        assert not outcome.complete
        assert outcome.outstanding == ["LMC-09"]

    def test_unevaluated_items_are_pending_not_passed(self, delivery_model) -> None:
        """Defaulting the other way is how checklists stop meaning anything."""
        checklist = delivery_model.checklists[CHECKLIST]
        items = delivery_model.items_for(CHECKLIST)
        outcome = evaluate_checklist(checklist, items, [])
        assert not outcome.complete
        assert all(o.status is ChecklistItemStatus.PENDING for o in outcome.items)
        assert len(unevaluated_items(items, [])) == len(items)

    def test_optional_items_do_not_block(self, delivery_model) -> None:
        checklist = delivery_model.checklists[CHECKLIST]
        items = delivery_model.items_for(CHECKLIST)
        mandatory_only = [i for i in items if i.mandatory]
        outcome = evaluate_checklist(checklist, items, _pass_all(mandatory_only))
        assert outcome.complete
        assert outcome.completion < 1.0

    def test_evidence_required_item_fails_without_evidence(self, delivery_model) -> None:
        """A pass with no evidence is an assertion, not a control."""
        checklist = delivery_model.checklists[CHECKLIST]
        items = delivery_model.items_for(CHECKLIST)
        results = [
            ChecklistItemResult(item_key=i.item_key, status=ChecklistItemStatus.PASS)
            for i in items
        ]
        outcome = evaluate_checklist(checklist, items, results)
        assert "LMC-01" in outcome.outstanding  # requires evidence, none supplied

    def test_not_applicable_leaves_the_denominator(self, delivery_model) -> None:
        checklist = delivery_model.checklists[CHECKLIST]
        items = delivery_model.items_for(CHECKLIST)
        results = _pass_all(items, skip={"LMC-10"})
        results.append(
            ChecklistItemResult(item_key="LMC-10", status=ChecklistItemStatus.NOT_APPLICABLE)
        )
        outcome = evaluate_checklist(checklist, items, results)
        assert outcome.completion == pytest.approx(1.0)
        assert outcome.not_applicable == ["LMC-10"]

    def test_percentage_rule_still_requires_mandatory_items(self, delivery_model) -> None:
        """Otherwise '90% complete' could mean every mandatory item failed."""
        checklist = delivery_model.checklists["test-checklist"]
        assert checklist.completion_rule is CompletionRule.PERCENTAGE
        items = delivery_model.items_for("test-checklist")
        outcome = evaluate_checklist(checklist, items, _pass_all(items, skip={"TST-02"}))
        assert not outcome.complete
        assert "TST-02" in outcome.outstanding

    def test_percentage_rule_needs_a_declared_threshold(self, delivery_model) -> None:
        checklist = delivery_model.checklists[CHECKLIST]
        with pytest.raises(ValidationError, match="not a rule"):
            checklist.model_copy(
                update={"completion_rule": CompletionRule.PERCENTAGE}
            ).model_validate(
                {
                    **checklist.model_dump(),
                    "completion_rule": "PERCENTAGE",
                    "completion_threshold": None,
                }
            )

    def test_machine_evaluable_share_is_reported(self, delivery_model) -> None:
        items = delivery_model.items_for(CHECKLIST)
        assert machine_evaluable_share(items) == pytest.approx(0.75)
        assert machine_evaluable_share([]) == 0.0


class TestWaivers:
    def _waiver(self, **kwargs: object) -> Waiver:
        return Waiver(
            reason="Peer reviewer unavailable; reviewed by the architect instead.",
            approver="head-of-data",
            evidence_ref=ref(EntityType.EVIDENCE, "ev-waiver"),
            **kwargs,  # type: ignore[arg-type]
        )

    def test_waiver_satisfies_an_item(self, delivery_model) -> None:
        checklist = delivery_model.checklists[CHECKLIST]
        items = delivery_model.items_for(CHECKLIST)
        results = _pass_all(items, skip={"LMC-09"})
        results.append(
            ChecklistItemResult(
                item_key="LMC-09", status=ChecklistItemStatus.WAIVED, waiver=self._waiver()
            )
        )
        outcome = evaluate_checklist(checklist, items, results)
        assert outcome.complete
        assert outcome.waived == ["LMC-09"]

    def test_unattributed_waiver_is_rejected_at_construction(self) -> None:
        with pytest.raises(ValidationError, match="carries no waiver"):
            ChecklistItemResult(item_key="LMC-09", status=ChecklistItemStatus.WAIVED)

    def test_waiver_on_a_non_waived_item_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="only makes sense on a WAIVED item"):
            ChecklistItemResult(
                item_key="LMC-09", status=ChecklistItemStatus.PASS, waiver=self._waiver()
            )

    def test_expired_waiver_stops_counting(self, delivery_model, fixed_now) -> None:
        """A temporary exception must not silently become permanent."""
        checklist = delivery_model.checklists[CHECKLIST]
        items = delivery_model.items_for(CHECKLIST)
        results = _pass_all(items, skip={"LMC-09"})
        results.append(
            ChecklistItemResult(
                item_key="LMC-09",
                status=ChecklistItemStatus.WAIVED,
                waiver=self._waiver(expires_at=fixed_now.replace(year=fixed_now.year - 1)),
            )
        )
        outcome = evaluate_checklist(checklist, items, results, now=fixed_now)
        assert not outcome.complete
        assert "LMC-09" in outcome.outstanding


class TestGateReadiness:
    def _complete_state(self, delivery_model, **overrides) -> GateState:
        items = delivery_model.items_for(CHECKLIST)
        outcome = evaluate_checklist(
            delivery_model.checklists[CHECKLIST], items, _pass_all(items)
        )
        defaults = {
            "present_artifact_kinds": {"logical-data-model", "traceability-matrix"},
            "checklist_outcomes": {CHECKLIST: outcome},
            "satisfied_evidence": {"ev.logical-model", "ev.traceability"},
            "approvals": {"data-architect"},
            "traceability": 1.0,
        }
        return GateState(**{**defaults, **overrides})

    def test_everything_in_place_passes(self, delivery_model) -> None:
        readiness = assess_gate(
            delivery_model.gates[GATE], self._complete_state(delivery_model)
        )
        assert readiness.status is GateStatus.PASS
        assert readiness.overall_score == pytest.approx(1.0)
        assert not readiness.blocking_items

    def test_missing_artifact_blocks_with_a_named_reason(self, delivery_model) -> None:
        state = self._complete_state(
            delivery_model, present_artifact_kinds={"logical-data-model"}
        )
        readiness = assess_gate(delivery_model.gates[GATE], state)
        assert readiness.status is GateStatus.BLOCKED
        assert any(
            item.requirement == "traceability-matrix" for item in readiness.blocking_items
        )

    def test_missing_approval_blocks(self, delivery_model) -> None:
        state = self._complete_state(delivery_model, approvals=set())
        readiness = assess_gate(delivery_model.gates[GATE], state)
        assert readiness.status is GateStatus.BLOCKED
        assert readiness.dimension(GateDimension.APPROVALS).score == 0.0

    def test_short_traceability_is_conditional_not_blocked(self, delivery_model) -> None:
        """The §10 worked example: everything green except traceability at 87%."""
        state = self._complete_state(delivery_model, traceability=0.87)
        readiness = assess_gate(delivery_model.gates[GATE], state)
        assert readiness.status is GateStatus.CONDITIONAL
        assert readiness.is_passable
        assert readiness.advisory_items
        assert readiness.dimension(GateDimension.TRACEABILITY).score == pytest.approx(0.87)

    def test_advisory_gate_never_blocks(self, delivery_model) -> None:
        """An advisory gate that halts delivery is not advisory."""
        gate = delivery_model.gates[GATE].model_copy(update={"blocking": False})
        state = self._complete_state(delivery_model, approvals=set())
        readiness = assess_gate(gate, state)
        assert readiness.status is GateStatus.CONDITIONAL
        assert readiness.is_passable

    def test_blocking_items_name_their_control(self, delivery_model) -> None:
        """A blocker a reviewer cannot trace to a rule is one they will override."""
        state = self._complete_state(delivery_model, satisfied_evidence=set())
        readiness = assess_gate(delivery_model.gates[GATE], state)
        for item in readiness.blocking_items:
            assert item.requirement
            assert item.detail

    def test_unevaluated_checklist_blocks(self, delivery_model) -> None:
        state = self._complete_state(delivery_model, checklist_outcomes={})
        readiness = assess_gate(delivery_model.gates[GATE], state)
        assert readiness.status is GateStatus.BLOCKED
        assert any("not been evaluated" in (i.detail or "") for i in readiness.blocking_items)

    def test_scores_are_exportable_for_the_audit_record(self, delivery_model) -> None:
        readiness = assess_gate(
            delivery_model.gates[GATE], self._complete_state(delivery_model)
        )
        scores = readiness.scores()
        assert set(scores) == {d.value for d in GateDimension}
        assert all(0.0 <= v <= 1.0 for v in scores.values())

    def test_render_produces_the_dashboard_view(self, delivery_model) -> None:
        readiness = assess_gate(
            delivery_model.gates[GATE], self._complete_state(delivery_model, traceability=0.87)
        )
        rendered = readiness.render()
        assert "Traceability" in rendered
        assert "CONDITIONAL" in rendered

    def test_gate_requiring_nothing_is_rejected_at_construction(self, delivery_model) -> None:
        """A gate with no requirements passes everything while looking like control."""
        gate = delivery_model.gates[GATE]
        with pytest.raises(ValidationError, match="requires nothing at all"):
            type(gate).model_validate(
                {
                    **gate.model_dump(),
                    "required_artifact_kinds": [],
                    "required_checklist_refs": [],
                    "required_evaluation_refs": [],
                    "required_evidence_refs": [],
                    "required_role_keys": [],
                    "rule_refs": [],
                }
            )
