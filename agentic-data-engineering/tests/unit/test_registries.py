"""Registry loading, cross-registry integrity, portability and the delivery model.

The registries are edited as data by people who may never run the suite, so
these are the guardrail. A role demanding a capability nobody defined, a task
pointing at a checklist that does not exist, or a phase graph with a cycle all
fail here rather than as an empty query result later.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from domain.metamodel.enums import (
    ActionClass,
    ApprovalLevel,
    AutomationLevel,
    EntityType,
    ProvenanceState,
)
from domain.metamodel.registry import MetamodelRegistry, RegistryError
from domain.metamodel.version import METAMODEL_VERSION


class TestLoading:
    def test_loads_every_registry(self, registry) -> None:
        assert registry.capabilities
        assert registry.delivery_capabilities
        assert registry.responsibilities
        assert registry.engineering_roles
        assert registry.delivery_roles
        assert registry.relationship_types
        assert registry.technology_bindings
        assert registry.delivery_models

    def test_declared_version_matches_code(self, registry) -> None:
        assert registry.declared_version == METAMODEL_VERSION


class TestReferentialIntegrity:
    def test_every_role_capability_exists(self, registry) -> None:
        for key, role in registry.engineering_roles.items():
            for capability in role.required_capabilities:
                assert capability in registry.capabilities, f"{key} -> {capability}"
            for capability in role.required_delivery_capabilities:
                assert capability in registry.delivery_capabilities, f"{key} -> {capability}"

    def test_every_relationship_endpoint_is_a_real_entity_type(self, registry) -> None:
        known = set(EntityType)
        for key, spec in registry.relationship_types.items():
            for endpoint in (*spec.source_types, *spec.target_types):
                assert endpoint in known, f"{key} references {endpoint}"

    def test_the_graph_spans_both_twins(self, registry) -> None:
        """Cross-twin edges are what make this one model rather than two."""
        cross = [s for s in registry.relationship_types.values() if s.is_cross_twin]
        assert len(cross) >= 10
        keys = {s.key for s in cross}
        assert {"GOVERNS", "DESCRIBES", "TRIGGERS_TASK", "TRACED_TO", "SATISFIES"} <= keys

    def test_every_provenance_state_has_a_rule(self, registry) -> None:
        assert set(registry.provenance_rules) == set(ProvenanceState)

    def test_inferred_may_not_block(self, registry) -> None:
        assert not registry.provenance_rules[ProvenanceState.INFERRED].may_block


class TestRoleChain:
    """DeliveryRole → EngineeringResponsibility → EngineeringRole → Agent."""

    def test_delivery_roles_map_to_real_responsibilities(self, registry) -> None:
        for key, role in registry.delivery_roles.items():
            for responsibility in role.responsibility_keys:
                assert responsibility in registry.responsibilities, f"{key} -> {responsibility}"

    def test_chain_resolves_end_to_end(self, registry) -> None:
        chain = registry.resolve_role_chain("data-architect")
        assert "resp.logical-data-design" in chain
        assert "data-model-engineer" in chain["resp.logical-data-design"]

    def test_non_delegable_responsibilities_name_no_engineering_role(self, registry) -> None:
        """A human accountability must not be assigned to agent-implemented work."""
        for key, responsibility in registry.responsibilities.items():
            if not responsibility.delegable_to_agent:
                assert responsibility.fulfilled_by_role_keys == [], key

    def test_delivery_and_engineering_roles_are_distinct_objects(self, registry) -> None:
        """Both catalogs contain 'data-architect' and they are not the same thing."""
        delivery = registry.delivery_role("data-architect")
        engineering = registry.role("data-architect")
        assert delivery is not None and engineering is not None
        # The delivery role carries a sign-off the engineering role cannot.
        assert "resp.architecture-signoff" in delivery.responsibility_keys
        assert "resp.architecture-signoff" not in engineering.responsibilities

    def test_segregation_of_duties_is_recorded(self, registry) -> None:
        test_lead = registry.delivery_role("test-lead")
        assert test_lead.is_segregated
        assert "data-engineer" in test_lead.incompatible_with


class TestApprovalPolicy:
    @pytest.mark.parametrize(
        ("action_class", "expected"),
        [
            (ActionClass.READ_ONLY, ApprovalLevel.NONE),
            (ActionClass.LOW_RISK_WRITE, ApprovalLevel.NONE),
            (ActionClass.HIGH_RISK_WRITE, ApprovalLevel.SINGLE_REVIEWER),
            (ActionClass.DESTRUCTIVE, ApprovalLevel.MAKER_CHECKER),
        ],
    )
    def test_assisted_mode_matrix(self, registry, action_class, expected) -> None:
        assert registry.required_approval(action_class, AutomationLevel.ASSISTED) is expected

    def test_destructive_always_needs_a_human(self, registry) -> None:
        for level in AutomationLevel:
            approval = registry.required_approval(ActionClass.DESTRUCTIVE, level)
            assert approval not in (ApprovalLevel.NONE, ApprovalLevel.SAMPLED_QA)

    def test_unknown_combination_defaults_to_strictest(self, registry) -> None:
        registry.approval_matrix.pop(AutomationLevel.AUTONOMOUS, None)
        assert (
            registry.required_approval(ActionClass.READ_ONLY, AutomationLevel.AUTONOMOUS)
            is ApprovalLevel.MAKER_CHECKER
        )


class TestPortability:
    def test_streaming_resolves_differently_per_platform(self, registry) -> None:
        gcp = {t for b in registry.bindings_for("streaming", "gcp") for t in b.technologies}
        aws = {t for b in registry.bindings_for("streaming", "aws") for t in b.technologies}
        assert "pubsub" in gcp and "kinesis" in aws
        assert not gcp & aws, "platform bindings must not leak into each other"

    def test_capability_answer_is_platform_independent(self, registry) -> None:
        for platform in ("gcp", "aws"):
            bindings = registry.bindings_for("streaming", platform)
            assert bindings and all(b.capability_key == "streaming" for b in bindings)

    def test_neutral_bindings_apply_everywhere(self, registry) -> None:
        for platform in ("gcp", "aws"):
            technologies = {
                t for b in registry.bindings_for("transformation", platform) for t in b.technologies
            }
            assert "dbt" in technologies

    def test_unbound_platform_returns_nothing_rather_than_guessing(self, registry) -> None:
        assert registry.bindings_for("streaming", "azure") == []


class TestWorkedDeliveryModel:
    def test_model_loads_with_all_its_parts(self, delivery_model) -> None:
        assert len(delivery_model.phases) == 9
        assert "task.logical-data-model" in delivery_model.tasks
        assert "logical-model-checklist" in delivery_model.checklists
        assert "gate.data-architecture-review" in delivery_model.gates

    def test_the_worked_task_matches_the_specification(self, delivery_model) -> None:
        """§6, asserted rather than described."""
        task = delivery_model.tasks["task.logical-data-model"]
        assert task.phase_keys == ["design"]
        assert set(task.required_skill_keys) == {
            "conceptual-model-analysis",
            "logical-model-generation",
            "traceability-mapping",
        }
        assert task.delivery_role_keys == ["data-architect"]
        assert [r.id for r in task.checklist_refs] == ["logical-model-checklist"]
        assert [r.id for r in task.approval_gate_refs] == ["gate.data-architecture-review"]

    def test_ac_ldm_07_is_machine_evaluable(self, delivery_model) -> None:
        """§9's worked criterion is a metadata lookup, not a matter of opinion."""
        criterion = delivery_model.criteria["AC-LDM-07"]
        assert "business owner" in criterion.condition
        assert criterion.is_machine_evaluable
        assert criterion.blocking

    def test_checklist_has_twelve_items(self, delivery_model) -> None:
        assert len(delivery_model.items_for("logical-model-checklist")) == 12

    def test_phases_are_ordered_and_acyclic(self, delivery_model) -> None:
        ordered = delivery_model.phases_in_order()
        assert [p.phase_key for p in ordered][:4] == [
            "discovery",
            "requirements",
            "architecture",
            "design",
        ]
        # Every dependency appears earlier in sequence than its dependent.
        position = {p.phase_key: p.sequence for p in ordered}
        for phase in ordered:
            for dependency in phase.depends_on_phase_keys:
                assert position[dependency] < phase.sequence

    def test_contracts_are_derived_for_controlled_tasks(self, delivery_model) -> None:
        contract = delivery_model.contract_for("task.logical-data-model")
        assert contract is not None
        assert contract.checklist_refs and contract.approval_gate_refs
        assert "logical-data-model" in contract.required_artifact_kinds

    def test_registry_model_may_block_because_it_is_verified(self, delivery_model) -> None:
        """Hand-written models are HUMAN_VERIFIED, so their gates can block."""
        gate = delivery_model.gates["gate.data-architecture-review"]
        assert gate.blocking
        assert gate.is_factual

    def test_feasibility_assessment_is_covered(self, delivery_model) -> None:
        """Closed coverage gap: feasibility was previously absent entirely."""
        task = delivery_model.tasks["task.feasibility-assessment"]
        assert task.phase_keys == ["discovery"]
        assert task.delivery_role_keys == ["business-analyst"]
        assert [r.id for r in task.checklist_refs] == ["feasibility-checklist"]
        assert set(delivery_model.criteria) >= {"AC-FEAS-01", "AC-FEAS-02"}
        # No formal gate: the discovery phase has none in this worked model, and
        # the verdict is recorded on the produced artifact instead. See ADR-0012.
        assert not task.approval_gate_refs

    def test_conceptual_model_task_satisfies_the_logical_model_input(self, delivery_model) -> None:
        """Closed coverage gap: the input existed, nothing produced it."""
        producing_task = delivery_model.tasks["task.conceptual-model"]
        assert producing_task.phase_keys == ["architecture"]
        output_kinds = {o.id for o in producing_task.output_refs}
        assert "out.conceptual-model" in output_kinds
        produced_artifact_kind = delivery_model.outputs["out.conceptual-model"].artifact_kind

        consuming_input = delivery_model.inputs["in.conceptual-model"]
        assert consuming_input.satisfied_by_artifact_kind == produced_artifact_kind

    def test_data_profiling_task_is_covered(self, delivery_model) -> None:
        """Closed coverage gap: profiling was a skill name with nowhere to land."""
        task = delivery_model.tasks["task.data-profiling"]
        assert task.phase_keys == ["testing"]
        assert "data-profiling" in task.required_skill_keys
        assert [r.id for r in task.evidence_requirement_refs] == ["ev.profiling-result"]

    def test_gate_count_grew_with_security_review(self, delivery_model) -> None:
        assert "gate.security-review" in delivery_model.gates


class TestValidationFailures:
    """Broken registries fail loudly at load, not silently at query time."""

    @staticmethod
    def _write(root: Path, **overrides: str) -> Path:
        files = {
            "metamodel.version.yaml": f"version: {METAMODEL_VERSION}\n",
            "capabilities.yaml": "version: 0.1.0\ncapabilities:\n  - key: streaming\n    name: Streaming\n",
            "delivery_capabilities.yaml": (
                "version: 0.1.0\ndelivery_capabilities:\n"
                "  - key: change-assurance\n    name: Change Assurance\n"
            ),
            "relationship_types.yaml": textwrap.dedent(
                """
                version: 0.1.0
                relationship_types:
                  - key: DEPENDS_ON
                    source_types: [Pipeline]
                    target_types: [DataAsset]
                """
            ),
            "engineering_responsibilities.yaml": textwrap.dedent(
                """
                version: 0.1.0
                engineering_responsibilities:
                  - key: resp.change
                    name: Change
                    statement: Assess changes.
                    required_capabilities: [streaming]
                    required_delivery_capabilities: [change-assurance]
                    fulfilled_by_roles: [pipeline-engineer]
                """
            ),
            "engineering_roles.yaml": textwrap.dedent(
                """
                version: 0.1.0
                engineering_roles:
                  - key: pipeline-engineer
                    name: Pipeline Engineer
                    mission: Keep pipelines working.
                    responsibilities: [resp.change]
                    required_capabilities: [streaming]
                """
            ),
            "delivery_roles.yaml": textwrap.dedent(
                """
                version: 0.1.0
                delivery_roles:
                  - key: data-engineer
                    name: Data Engineer
                    responsibilities: [resp.change]
                """
            ),
            "skills.yaml": "version: 0.1.0\nskills: []\n",
            "tools.yaml": "version: 0.1.0\ntools: []\n",
            "knowledge_packs.yaml": "version: 0.1.0\nknowledge_packs: []\n",
            "agents.yaml": "version: 0.1.0\nagents: []\n",
            "evaluation_metrics.yaml": "version: 0.1.0\nevaluation_metrics: []\n",
            "evaluation_scenarios.yaml": "version: 0.1.0\nevaluation_scenarios: []\n",
            "evaluation_suites.yaml": "version: 0.1.0\nevaluation_suites: []\n",
            "platforms.yaml": textwrap.dedent(
                """
                version: 0.1.0
                platforms:
                  - key: gcp
                    name: GCP
                technology_bindings:
                  - capability_key: streaming
                    platform_key: gcp
                    technologies: [pubsub]
                """
            ),
            "provenance.yaml": textwrap.dedent(
                """
                version: 0.1.0
                provenance_states:
                  - {key: OBSERVED, name: Observed, rank: 2, may_block: true}
                  - {key: INFERRED, name: Inferred, rank: 1, may_block: false}
                  - {key: HUMAN_VERIFIED, name: Human Verified, rank: 3, may_block: true}
                  - {key: CERTIFIED, name: Certified, rank: 4, may_block: true}
                """
            ),
            "risk.yaml": textwrap.dedent(
                """
                version: 0.1.0
                approval_matrix:
                  ASSISTED: {READ_ONLY: NONE, LOW_RISK_WRITE: NONE, HIGH_RISK_WRITE: SINGLE_REVIEWER, DESTRUCTIVE: MAKER_CHECKER}
                  SUPERVISED_AUTONOMOUS: {READ_ONLY: NONE, LOW_RISK_WRITE: SAMPLED_QA, HIGH_RISK_WRITE: SINGLE_REVIEWER, DESTRUCTIVE: MAKER_CHECKER}
                  AUTONOMOUS: {READ_ONLY: NONE, LOW_RISK_WRITE: NONE, HIGH_RISK_WRITE: SINGLE_REVIEWER, DESTRUCTIVE: MAKER_CHECKER}
                """
            ),
        }
        files.update(overrides)
        root.mkdir(parents=True, exist_ok=True)
        for name, body in files.items():
            (root / name).write_text(body, encoding="utf-8")
        return root

    def test_baseline_fixture_is_valid(self, tmp_path: Path) -> None:
        """Guards the negative tests: they must fail for the stated reason."""
        assert MetamodelRegistry.load(self._write(tmp_path / "ok"))

    def test_role_requiring_unknown_capability_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "bad-role",
            **{
                "engineering_roles.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    engineering_roles:
                      - key: ghost
                        name: Ghost
                        mission: Requires the undefined.
                        required_capabilities: [teleportation]
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="teleportation"):
            MetamodelRegistry.load(root)

    def test_version_mismatch_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(tmp_path / "bad-version", **{"metamodel.version.yaml": "version: 9.9.9\n"})
        with pytest.raises(RegistryError, match="must agree"):
            MetamodelRegistry.load(root)

    def test_automatable_destruction_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "unsafe",
            **{
                "risk.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    approval_matrix:
                      ASSISTED: {READ_ONLY: NONE, LOW_RISK_WRITE: NONE, HIGH_RISK_WRITE: SINGLE_REVIEWER, DESTRUCTIVE: MAKER_CHECKER}
                      SUPERVISED_AUTONOMOUS: {READ_ONLY: NONE, LOW_RISK_WRITE: SAMPLED_QA, HIGH_RISK_WRITE: SINGLE_REVIEWER, DESTRUCTIVE: MAKER_CHECKER}
                      AUTONOMOUS: {READ_ONLY: NONE, LOW_RISK_WRITE: NONE, HIGH_RISK_WRITE: NONE, DESTRUCTIVE: NONE}
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="destructive actions always require"):
            MetamodelRegistry.load(root)

    def test_non_delegable_responsibility_with_a_role_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "delegation",
            **{
                "engineering_responsibilities.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    engineering_responsibilities:
                      - key: resp.change
                        name: Change
                        statement: Sign off changes.
                        required_capabilities: [streaming]
                        fulfilled_by_roles: [pipeline-engineer]
                        delegable_to_agent: false
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="non-delegable accountability"):
            MetamodelRegistry.load(root)

    def test_phase_cycle_is_rejected(self, tmp_path: Path) -> None:
        """A delivery model with a cycle is unsatisfiable."""
        root = self._write(tmp_path / "cycle")
        models = root / "delivery-models"
        models.mkdir(exist_ok=True)
        (models / "looping.yaml").write_text(
            textwrap.dedent(
                """
                version: 0.1.0
                model:
                  key: looping
                  name: Looping Model
                phases:
                  - {key: a, name: A, sequence: 1, depends_on: [b]}
                  - {key: b, name: B, sequence: 2, depends_on: [a]}
                """
            ),
            encoding="utf-8",
        )
        with pytest.raises(RegistryError, match="dependency cycle"):
            MetamodelRegistry.load(root)

    def test_two_accountable_roles_for_one_task_is_rejected(self, tmp_path: Path) -> None:
        """Two accountable roles is an unresolvable escalation."""
        root = self._write(tmp_path / "raci")
        models = root / "delivery-models"
        models.mkdir(exist_ok=True)
        (models / "raci.yaml").write_text(
            textwrap.dedent(
                """
                version: 0.1.0
                model: {key: m, name: M}
                phases: [{key: p, name: P, sequence: 1}]
                tasks: [{key: t, name: T, phases: [p]}]
                raci:
                  - {task: t, accountable: data-engineer}
                  - {task: t, accountable: data-engineer, responsible: []}
                """
            ),
            encoding="utf-8",
        )
        with pytest.raises(RegistryError, match="accountable roles"):
            MetamodelRegistry.load(root)

    def test_dangling_approves_gate_reference_is_rejected(self, tmp_path: Path) -> None:
        """A role claiming authority over a gate that does not exist is a dangling
        reference that looks, at a glance, like real authority (Phase 2 fix)."""
        root = self._write(
            tmp_path / "phantom-gate",
            **{
                "delivery_roles.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    delivery_roles:
                      - key: data-engineer
                        name: Data Engineer
                        responsibilities: [resp.change]
                        approves_gates: [gate.phantom]
                    """
                )
            },
        )
        models = root / "delivery-models"
        models.mkdir(exist_ok=True)
        (models / "phantom.yaml").write_text(
            textwrap.dedent(
                """
                version: 0.1.0
                model: {key: m, name: M}
                phases: [{key: p, name: P, sequence: 1}]
                """
            ),
            encoding="utf-8",
        )
        with pytest.raises(RegistryError, match="claims it approves gate 'gate.phantom'"):
            MetamodelRegistry.load(root)

    def test_all_problems_reported_at_once(self, tmp_path: Path) -> None:
        """Fixing registry data one error per run is miserable."""
        root = self._write(
            tmp_path / "many",
            **{
                "metamodel.version.yaml": "version: 9.9.9\n",
                "engineering_roles.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    engineering_roles:
                      - key: ghost
                        name: Ghost
                        mission: Broken.
                        required_capabilities: [teleportation, time-travel]
                    """
                ),
            },
        )
        with pytest.raises(RegistryError) as exc:
            MetamodelRegistry.load(root)
        assert "registry problem(s)" in str(exc.value)
        assert str(exc.value).count("  - ") >= 3
