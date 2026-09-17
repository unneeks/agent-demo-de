"""The three acceptance criteria provable at this stage.

Most of the specification's criteria depend on discovery, the runtime or the
evaluation harness. Three are properties of the foundation itself, and if they
do not hold now no later phase can rescue them:

* **#19** -- agent versions are reproducible.
* **#20** -- an agent implementation can be replaced without changing the role.
* **Delivery conformance** (§15, §28) -- an agent that is technically capable
  but cannot discharge the organization's controls is rejected, with reasons.

The third is new with the addendum and is the one that distinguishes a digital
engineering organization from a collection of copilots.
"""

from __future__ import annotations

import json

import pytest

from domain.metamodel.entities.organization import DeliveryCapabilityDeclaration
from domain.metamodel.entities.shared.context import ContextItem, ContextPolicy
from domain.metamodel.entities.shared.work import Decision, Workflow
from domain.metamodel.enums import AgentLifecycle, EntityType, ExecutionModel
from domain.metamodel.relationships import relationship
from engines.context import assemble
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository
from tests.conftest import make_agent, make_context_item, make_policy, ref

ROLE = "regression-engineer"


class TestCriterion20RoleOutlivesTheAgent:
    """The role is the contract; the agent is an implementation detail."""

    def _capable(self, agent_id: str, registry, **kwargs):
        role = registry.role(ROLE)
        return make_agent(
            agent_id,
            ROLE,
            capabilities=list(role.required_capabilities),
            delivery_capabilities=list(role.required_delivery_capabilities),
            skills=list(role.required_skills),
            tools=list(role.required_tools),
            knowledge_packs=list(role.required_knowledge),
            **kwargs,
        )

    def test_two_different_implementations_both_satisfy_the_role(self, registry) -> None:
        role = registry.role(ROLE)
        # Different in every way that is not the role's business.
        incumbent = self._capable(
            "regression-agent-v1",
            registry,
            version="1.0.0",
            model_provider="provider-a",
            execution_model=ExecutionModel.PLANNER_EXECUTOR,
            max_iterations=10,
        )
        challenger = self._capable(
            "regression-agent-v2",
            registry,
            version="2.0.0",
            model_provider="provider-b",
            execution_model=ExecutionModel.ITERATIVE,
            max_iterations=25,
        )
        for agent in (incumbent, challenger):
            assert role.is_satisfied_by(
                capabilities=set(agent.capabilities),
                delivery_capabilities=set(agent.delivery_capabilities),
                skills=set(agent.skills),
                tools=set(agent.tools),
                knowledge=set(agent.knowledge_packs),
            ), f"{agent.id} should satisfy {role.role_key}"

    def test_swapping_the_agent_leaves_the_role_untouched(self, registry) -> None:
        role_snapshot = registry.role(ROLE).model_dump()
        graph = InMemoryGraphRepository()
        role_ref = ref(EntityType.ENGINEERING_ROLE, ROLE)

        graph.upsert_relationship(
            relationship(
                "IMPLEMENTED_BY", role_ref, ref(EntityType.AGENT, "regression-agent-v1", "1.0.0")
            )
        )
        graph.upsert_relationship(
            relationship(
                "IMPLEMENTED_BY", role_ref, ref(EntityType.AGENT, "regression-agent-v2", "2.0.0")
            )
        )

        implementations = graph.neighbors(role_ref, type_="IMPLEMENTED_BY")
        assert ref(EntityType.AGENT, "regression-agent-v2") in implementations
        assert registry.role(ROLE).model_dump() == role_snapshot

    def test_underqualified_agent_is_rejected_with_reasons(self, registry) -> None:
        role = registry.role(ROLE)
        missing = role.missing_requirements(
            capabilities={"testing"}, skills=set(), tools=set()
        )
        assert "regression-testing" in missing["capabilities"]
        assert "regression-assurance" in missing["delivery_capabilities"]
        assert missing["tools"]

    def test_workflows_bind_to_roles_not_agents(self, registry) -> None:
        """If workflows named agents, replacing one would rewrite every workflow."""
        workflow = Workflow(
            id="pr-review",
            name="Pull request review",
            entity_type=EntityType.WORKFLOW,
            workflow_key="pr-review",
            trigger="pull_request.opened",
            participating_role_keys=[ROLE],
            delivery_task_keys=["task.regression-test"],
        )
        assert all(registry.role(k) is not None for k in workflow.participating_role_keys)

    def test_four_level_chain_survives_agent_replacement(self, registry) -> None:
        """DeliveryRole → Responsibility → EngineeringRole is stable above the agent."""
        chain = registry.resolve_role_chain("test-lead")
        assert "resp.regression-proof" in chain
        assert ROLE in chain["resp.regression-proof"]


class TestDeliveryConformance:
    """§15 and §28: capability is necessary but not sufficient.

    'Can the agent do the work?' and 'can it do the work according to the
    organization's delivery model?' are separate questions, and the second is
    the one the original design could not ask.
    """

    CONTRACT = "contract.logical-data-model"

    def _contract(self, delivery_model):
        contract = delivery_model.contracts[self.CONTRACT]
        assert contract is not None
        return contract

    def _technically_capable_kwargs(self, contract) -> dict[str, object]:
        return {
            "capabilities": set(contract.required_capability_keys),
            "skills": set(contract.required_skill_keys),
            "tools": set(contract.required_tool_keys),
            "knowledge": set(contract.required_knowledge_keys),
        }

    def test_capable_and_conformant_agent_is_eligible(self, delivery_model) -> None:
        contract = self._contract(delivery_model)
        result = contract.conformance_of(
            agent_key="modelling-agent",
            **self._technically_capable_kwargs(contract),
            supported_checklists={r.id for r in contract.checklist_refs},
            supported_gates={r.id for r in contract.approval_gate_refs},
            supported_artifact_kinds=set(contract.required_artifact_kinds),
        )
        assert result.is_eligible
        assert not result.gaps

    def test_capable_but_non_conformant_agent_is_rejected(self, delivery_model) -> None:
        """The headline case. A perfectly capable agent that ignores the process."""
        contract = self._contract(delivery_model)
        result = contract.conformance_of(
            agent_key="copilot-agent", **self._technically_capable_kwargs(contract)
        )
        assert result.technically_capable
        assert not result.delivery_conformant
        assert not result.is_eligible

    def test_rejection_is_explained_not_just_refused(self, delivery_model) -> None:
        """A rejection nobody can act on is a rejection that gets overridden."""
        contract = self._contract(delivery_model)
        result = contract.conformance_of(
            agent_key="copilot-agent", **self._technically_capable_kwargs(contract)
        )
        dimensions = {gap.dimension for gap in result.blocking_gaps}
        assert {"checklist", "gate"} <= dimensions
        explanation = result.explain()
        assert "may not execute" in explanation
        assert "logical-model-checklist" in explanation

    def test_conformant_but_incapable_agent_is_also_rejected(self, delivery_model) -> None:
        """Both dimensions are required; neither substitutes for the other."""
        contract = self._contract(delivery_model)
        result = contract.conformance_of(
            agent_key="paperwork-agent",
            capabilities=set(),
            skills=set(),
            tools=set(),
            supported_checklists={r.id for r in contract.checklist_refs},
            supported_gates={r.id for r in contract.approval_gate_refs},
            supported_artifact_kinds=set(contract.required_artifact_kinds),
        )
        assert not result.technically_capable
        assert result.delivery_conformant
        assert not result.is_eligible

    def test_missing_knowledge_is_advisory_not_blocking(self, delivery_model) -> None:
        contract = self._contract(delivery_model)
        kwargs = self._technically_capable_kwargs(contract)
        kwargs["knowledge"] = set()
        result = contract.conformance_of(
            agent_key="agent",
            **kwargs,
            supported_checklists={r.id for r in contract.checklist_refs},
            supported_gates={r.id for r in contract.approval_gate_refs},
            supported_artifact_kinds=set(contract.required_artifact_kinds),
        )
        assert result.is_eligible or all(
            not gap.mandatory for gap in result.gaps if gap.dimension == "knowledge"
        )

    def test_agent_declares_what_it_supports_in_the_delivery_model(self) -> None:
        """§13: an agent claims organizational work, not just capability."""
        agent = make_agent(
            "modelling-agent",
            "data-model-engineer",
            delivery=DeliveryCapabilityDeclaration(
                supported_phase_keys=["design"],
                supported_task_keys=["task.logical-data-model"],
                supported_checklist_keys=["logical-model-checklist"],
                supported_artifact_kinds=["logical-data-model"],
                supported_gate_keys=["gate.data-architecture-review"],
            ),
        )
        assert "task.logical-data-model" in agent.delivery.supported_task_keys

    def test_contract_without_controls_is_refused(self, delivery_model) -> None:
        """Otherwise every agent satisfies it vacuously."""
        contract = self._contract(delivery_model)
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="vacuously"):
            type(contract).model_validate(
                {
                    **contract.model_dump(),
                    "checklist_refs": [],
                    "acceptance_criterion_refs": [],
                    "approval_gate_refs": [],
                }
            )

    def test_non_delegable_responsibility_names_no_engineering_role(self, registry) -> None:
        """Some accountability is not delegable however good the agent."""
        signoff = registry.responsibility("resp.architecture-signoff")
        assert not signoff.delegable_to_agent
        assert signoff.fulfilled_by_role_keys == []


class TestCriterion19Reproducibility:
    def test_identical_inputs_produce_an_identical_bundle(self, fixed_now) -> None:
        policy = make_policy("pr-review", max_tokens=1000, version="1.0.0")
        items = [
            make_context_item(f"i{n}", priority=n, tokens=100, now=fixed_now) for n in range(6)
        ]
        first = assemble(policy, items, now=fixed_now)
        second = assemble(policy, items, now=fixed_now)
        assert first.bundle_hash == second.bundle_hash
        assert first.manifest() == second.manifest()

    def test_replaying_a_snapshot_reproduces_the_hash(self, fixed_now) -> None:
        """The reproducibility loop in miniature: serialize, discard, rehydrate."""
        from datetime import datetime

        policy = make_policy("pr-review", max_tokens=400, version="1.0.0")
        items = [
            make_context_item(f"i{n}", priority=n, tokens=100, now=fixed_now) for n in range(5)
        ]
        original = assemble(policy, items, now=fixed_now)

        snapshot = json.dumps(
            {
                "policy": policy.model_dump(mode="json"),
                "items": [item.model_dump(mode="json") for item in items],
                "assembled_at": fixed_now.isoformat(),
            },
            sort_keys=True,
        )
        restored = json.loads(snapshot)
        replayed = assemble(
            ContextPolicy.model_validate(restored["policy"]),
            [ContextItem.model_validate(raw) for raw in restored["items"]],
            now=datetime.fromisoformat(restored["assembled_at"]),
        )
        assert replayed.bundle_hash == original.bundle_hash

    def test_a_decision_pins_every_component_version(self, fixed_now, delivery_model) -> None:
        """A decision that cannot name its inputs cannot be re-derived."""
        policy = make_policy("pr-review", max_tokens=500, version="1.0.0")
        bundle = assemble(
            policy, [make_context_item("i1", tokens=50, now=fixed_now)], now=fixed_now
        )
        contract = delivery_model.contracts["contract.logical-data-model"]

        decision = Decision(
            id="dec-1",
            name="Recommend regression run",
            entity_type=EntityType.DECISION,
            summary="Selected 4 regression tests covering the two impacted marts.",
            outcome="recommend",
            agent_ref=ref(EntityType.AGENT, "regression-agent-v1", "1.0.0"),
            contract_ref=ref(EntityType.DELIVERY_CONTRACT, contract.contract_key, "0.1.0"),
            context_bundle_ref=ref(EntityType.CONTEXT_BUNDLE, bundle.id, bundle.version),
            gate_readiness={"CHECKLISTS": 1.0, "TRACEABILITY": 0.87},
            component_versions={
                "metamodel": "0.1.0",
                "agent": "1.0.0",
                "delivery_model": "0.1.0",
                "context_policy": "1.0.0",
                "project_snapshot": "abc123def",
            },
        )
        assert decision.agent_ref.version == "1.0.0"
        assert decision.contract_ref is not None
        assert decision.component_versions["project_snapshot"] == "abc123def"
        assert decision.gate_readiness["TRACEABILITY"] == 0.87

    def test_superseded_agent_versions_stay_retrievable(self) -> None:
        repo = InMemoryMetadataRepository()
        repo.upsert(make_agent("regression-agent", ROLE, version="1.0.0"))
        repo.upsert(
            make_agent("regression-agent", ROLE, version="2.0.0", status=AgentLifecycle.DRAFT)
        )
        assert repo.versions(EntityType.AGENT, "regression-agent") == ["1.0.0", "2.0.0"]
        historical = repo.get(EntityType.AGENT, "regression-agent", version="1.0.0")
        assert historical is not None and not historical.is_current

    def test_stored_entities_record_their_metamodel_version(self) -> None:
        repo = InMemoryMetadataRepository()
        stored = repo.upsert(make_agent("a", ROLE))
        assert stored.metamodel_version and stored.content_hash
