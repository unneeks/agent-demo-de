"""Dual impact analysis and traceability.

The §20 and §27 behaviours: a change resolves to both a technical blast radius
and a set of delivery obligations, and a requirement can be traced to its
deployment -- or to the exact point where the chain breaks.
"""

from __future__ import annotations

import pytest

from domain.metamodel.enums import EntityType, ProvenanceState, RiskClass
from domain.metamodel.relationships import relationship
from engines.impact import (
    analyze_impact,
    analyze_technical_impact,
    trace,
    traceability_score,
)
from tests.conftest import make_change, ref


@pytest.fixture
def twin(graph):
    """A small but complete dual twin.

    Technical:  customer_address.sql <- stg_customers <- mart_customer_360 <- test
    Delivery:   task.logical-data-model GOVERNS stg_customers
                logical-data-model-v3 DESCRIBES mart_customer_360 (inferred, 0.7)
    """
    sql = ref(EntityType.CODE_ARTIFACT, "customer_address.sql")
    stg = ref(EntityType.PIPELINE, "stg_customers")
    mart = ref(EntityType.PIPELINE, "mart_customer_360")
    test = ref(EntityType.TEST, "test_customer_360")
    task = ref(EntityType.DELIVERY_TASK, "task.logical-data-model")
    doc = ref(EntityType.DELIVERY_ARTIFACT, "logical-data-model-v3")

    graph.upsert_relationship(relationship("DEPENDS_ON", stg, sql, discovered_by="dbt"))
    graph.upsert_relationship(relationship("DEPENDS_ON", mart, stg, discovered_by="dbt"))
    graph.upsert_relationship(relationship("COVERS", test, mart, discovered_by="pytest"))
    graph.upsert_relationship(relationship("GOVERNS", task, stg, discovered_by="delivery"))
    graph.upsert_relationship(
        relationship(
            "DESCRIBES",
            doc,
            mart,
            provenance=ProvenanceState.INFERRED,
            confidence=0.7,
            discovered_by="doc-extractor",
        )
    )
    return graph


class TestTechnicalImpact:
    def test_finds_the_downstream_blast_radius(self, twin) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")])
        impact = analyze_technical_impact(change, twin)
        reached = {r.ref.id for r in impact.impacted}
        assert reached == {
            "customer_address.sql",
            "stg_customers",
            "mart_customer_360",
            "test_customer_360",
        }

    def test_the_changed_thing_is_itself_impacted(self, twin) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")])
        impact = analyze_technical_impact(change, twin)
        seed = next(r for r in impact.impacted if r.ref.id == "customer_address.sql")
        assert seed.depth == 0 and seed.confidence == 1.0

    def test_tests_are_selected_from_the_blast_radius(self, twin) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")])
        impact = analyze_technical_impact(change, twin)
        assert [t.id for t in impact.selected_tests] == ["test_customer_360"]

    def test_depth_limits_the_walk(self, twin) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")])
        impact = analyze_technical_impact(change, twin, max_depth=1)
        assert {r.ref.id for r in impact.impacted} == {"customer_address.sql", "stg_customers"}

    def test_unrelated_change_has_no_reach(self, twin) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "unrelated.sql")])
        impact = analyze_technical_impact(change, twin)
        assert [r.ref.id for r in impact.impacted] == ["unrelated.sql"]


class TestDeliveryImpact:
    def test_change_triggers_the_governing_task(self, twin, delivery_model) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")])
        impact = analyze_impact(change, twin, delivery_model)
        assert [o.key for o in impact.delivery.triggered_tasks] == ["task.logical-data-model"]

    def test_task_expands_into_its_controls(self, twin, delivery_model) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")])
        impact = analyze_impact(change, twin, delivery_model)
        assert "logical-model-checklist" in [o.key for o in impact.delivery.required_checklists]
        assert "gate.data-architecture-review" in [o.key for o in impact.delivery.gates_to_clear]
        assert "ev.logical-model" in [o.key for o in impact.delivery.evidence_required]

    def test_required_approvers_are_resolved_from_the_gate(self, twin, delivery_model) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")])
        impact = analyze_impact(change, twin, delivery_model)
        assert [o.key for o in impact.delivery.required_approvers] == ["data-architect"]

    def test_documentation_drift_is_flagged_at_the_edge_confidence(
        self, twin, delivery_model
    ) -> None:
        """An inferred DESCRIBES must not read as certain.

        Acting on a low-confidence documentation edge means telling someone to
        update a document that was never about their code.
        """
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")])
        impact = analyze_impact(change, twin, delivery_model)
        doc = next(o for o in impact.delivery.documentation_to_update)
        assert doc.key == "logical-data-model-v3"
        assert doc.confidence == pytest.approx(0.7)
        assert not doc.mandatory

    def test_min_confidence_prunes_speculative_obligations(self, twin, delivery_model) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")])
        impact = analyze_impact(change, twin, delivery_model, min_confidence=0.8)
        assert not impact.delivery.documentation_to_update

    def test_risk_escalates_from_the_gate_not_only_the_diff(
        self, twin, delivery_model
    ) -> None:
        """A one-line change that trips a HIGH-risk gate is a HIGH-risk change.

        Only the delivery twin knows this; a purely technical analysis would
        report the change as low risk because it touched one file.
        """
        change = make_change(
            risk=RiskClass.LOW,
            impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")],
        )
        impact = analyze_impact(change, twin, delivery_model)
        assert change.risk is RiskClass.LOW
        assert impact.risk is RiskClass.HIGH

    def test_change_with_no_delivery_coupling_owes_nothing(self, twin, delivery_model) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "orphan.sql")])
        impact = analyze_impact(change, twin, delivery_model)
        assert impact.delivery.is_empty

    def test_render_reports_both_dimensions(self, twin, delivery_model) -> None:
        change = make_change(impacted_refs=[ref(EntityType.CODE_ARTIFACT, "customer_address.sql")])
        rendered = analyze_impact(change, twin, delivery_model).render()
        assert "Technical impact:" in rendered
        assert "Delivery impact:" in rendered


class TestTraceability:
    def _full_chain(self, graph) -> None:
        requirement = ref(EntityType.REQUIREMENT, "REQ-183")
        task = ref(EntityType.DELIVERY_TASK, "task.logical-data-model")
        agent = ref(EntityType.AGENT, "pipeline-engineering-agent")
        artifact = ref(EntityType.DELIVERY_ARTIFACT, "address_validation.sql")
        test = ref(EntityType.TEST, "TEST-91")
        evidence = ref(EntityType.EVIDENCE, "run-882")
        approval = ref(EntityType.APPROVAL, "GATE-17-approval")
        deployment = ref(EntityType.DEPLOYMENT, "release-2026-08")

        for edge, source, target in [
            ("TRACED_TO", requirement, task),
            ("PERFORMED_BY", task, agent),
            ("PRODUCES_ARTIFACT", agent, artifact),
            ("VERIFIED_BY", artifact, test),
            ("GENERATES", test, evidence),
            ("SUPPORTS_APPROVAL", evidence, approval),
            ("AUTHORIZES", approval, deployment),
        ]:
            graph.upsert_relationship(relationship(edge, source, target, discovered_by="fixture"))

    def test_complete_chain_resolves_end_to_end(self, graph) -> None:
        self._full_chain(graph)
        chain = trace(ref(EntityType.REQUIREMENT, "REQ-183"), graph)
        assert chain.is_complete
        assert chain.completeness == pytest.approx(1.0)
        assert chain.links[-1].found == [ref(EntityType.DEPLOYMENT, "release-2026-08")]

    def test_break_is_located_and_explained(self, graph) -> None:
        """The interesting output: where a requirement stops being demonstrable."""
        requirement = ref(EntityType.REQUIREMENT, "REQ-900")
        task = ref(EntityType.DELIVERY_TASK, "task.logical-data-model")
        graph.upsert_relationship(
            relationship("TRACED_TO", requirement, task, discovered_by="fixture")
        )
        chain = trace(requirement, graph)
        assert not chain.is_complete
        assert chain.broken_at == 1
        description = chain.break_description()
        assert "Agent" in description and "PERFORMED_BY" in description

    def test_completeness_counts_the_whole_chain(self, graph) -> None:
        requirement = ref(EntityType.REQUIREMENT, "REQ-900")
        graph.upsert_relationship(
            relationship(
                "TRACED_TO",
                requirement,
                ref(EntityType.DELIVERY_TASK, "task.logical-data-model"),
                discovered_by="fixture",
            )
        )
        chain = trace(requirement, graph)
        # One of seven links resolved.
        assert chain.completeness == pytest.approx(1 / 7)

    def test_orphan_requirement_traces_to_nothing(self, graph) -> None:
        chain = trace(ref(EntityType.REQUIREMENT, "REQ-000"), graph)
        assert chain.broken_at == 0
        assert chain.completeness == 0.0

    def test_render_marks_the_break(self, graph) -> None:
        requirement = ref(EntityType.REQUIREMENT, "REQ-900")
        graph.upsert_relationship(
            relationship(
                "TRACED_TO",
                requirement,
                ref(EntityType.DELIVERY_TASK, "task.logical-data-model"),
                discovered_by="fixture",
            )
        )
        rendered = trace(requirement, graph).render()
        assert "X " in rendered and "missing" in rendered

    def test_score_averages_across_requirements(self, graph) -> None:
        """Feeds GateState.traceability.

        Averaging chains rather than counting complete ones lets a gate tell
        "one requirement is untraceable" apart from "none has deployed yet".
        """
        self._full_chain(graph)
        # A second requirement pointing at a *different* task, one with nothing
        # downstream of it -- otherwise it would inherit the first chain.
        graph.upsert_relationship(
            relationship(
                "TRACED_TO",
                ref(EntityType.REQUIREMENT, "REQ-900"),
                ref(EntityType.DELIVERY_TASK, "task.build-pipeline"),
                discovered_by="fixture",
            )
        )
        score = traceability_score(
            [ref(EntityType.REQUIREMENT, "REQ-183"), ref(EntityType.REQUIREMENT, "REQ-900")],
            graph,
        )
        assert score == pytest.approx((1.0 + 1 / 7) / 2)

    def test_empty_input_scores_as_complete(self, graph) -> None:
        assert traceability_score([], graph) == 1.0
