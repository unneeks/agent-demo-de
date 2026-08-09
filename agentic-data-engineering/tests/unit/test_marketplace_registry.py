"""The marketplace catalog: skills/tools/knowledge_packs/agents registries.

Loading, cross-registry referential integrity, and the direct proof that the
worked catalog is real -- at least one loaded agent satisfies each of the 5
"staffed in the MVP" engineering roles via the pre-existing
EngineeringRole.is_satisfied_by(), not a redefinition of what "satisfies"
means. See ADR-0014.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from domain.metamodel.enums import ActionClass, ExecutionModel
from domain.metamodel.registry import MetamodelRegistry, RegistryError
from domain.metamodel.version import METAMODEL_VERSION

STAFFED_ROLES = (
    "regression-engineer",
    "impact-analysis-engineer",
    "data-quality-engineer",
    "data-model-engineer",
    "delivery-compliance-engineer",
)


class TestLoading:
    def test_catalogs_load_non_empty(self, registry) -> None:
        assert registry.skills
        assert registry.tools
        assert registry.knowledge_packs
        assert registry.agents


class TestReferentialIntegrity:
    def test_every_agent_role_key_resolves(self, registry) -> None:
        for key, agent in registry.agents.items():
            assert agent.role_key in registry.engineering_roles, key

    def test_every_agent_capability_resolves(self, registry) -> None:
        for key, agent in registry.agents.items():
            for capability in agent.capabilities:
                assert capability in registry.capabilities, (key, capability)
            for capability in agent.delivery_capabilities:
                assert capability in registry.delivery_capabilities, (key, capability)

    def test_every_agent_skill_tool_knowledge_resolves(self, registry) -> None:
        for key, agent in registry.agents.items():
            for skill in agent.skills:
                assert skill in registry.skills, (key, skill)
            for tool in agent.tools:
                assert tool in registry.tools, (key, tool)
            for pack in agent.knowledge_packs:
                assert pack in registry.knowledge_packs, (key, pack)

    def test_every_skill_tool_and_knowledge_reference_resolves(self, registry) -> None:
        for key, skill in registry.skills.items():
            for tool in skill.required_tools:
                assert tool in registry.tools, (key, tool)
            for pack in skill.required_knowledge:
                assert pack in registry.knowledge_packs, (key, pack)


class TestWorkedCatalogIsReal:
    @pytest.mark.parametrize("role_key", STAFFED_ROLES)
    def test_staffed_role_has_a_satisfying_agent(self, registry, role_key) -> None:
        role = registry.engineering_roles[role_key]
        satisfying = [
            agent
            for agent in registry.agents.values()
            if agent.role_key == role_key
            and role.is_satisfied_by(
                capabilities=set(agent.capabilities),
                delivery_capabilities=set(agent.delivery_capabilities),
                skills=set(agent.skills),
                tools=set(agent.tools),
                knowledge=set(agent.knowledge_packs),
            )
        ]
        assert satisfying, f"no agent in the catalog satisfies {role_key!r}"

    def test_external_agent_declares_a_provider(self, registry) -> None:
        agent = registry.agents["copilot-coding-agent-regression"]
        assert agent.execution_model is ExecutionModel.EXTERNAL_AGENT
        assert agent.external_provider == "github-copilot-coding-agent"

    def test_external_agent_partially_satisfies_its_role(self, registry) -> None:
        agent = registry.agents["copilot-coding-agent-regression"]
        role = registry.engineering_roles[agent.role_key]
        missing = role.missing_requirements(
            capabilities=set(agent.capabilities),
            delivery_capabilities=set(agent.delivery_capabilities),
            skills=set(agent.skills),
            tools=set(agent.tools),
            knowledge=set(agent.knowledge_packs),
        )
        assert missing["capabilities"]
        assert missing["delivery_capabilities"]
        assert missing["skills"]
        assert missing["knowledge"]
        assert missing["tools"] == []

    def test_github_tool_carries_the_copilot_review_action(self, registry) -> None:
        action = registry.tools["github"].action("copilot_code_review")
        assert action is not None
        assert action.action_class is ActionClass.LOW_RISK_WRITE

    def test_data_quality_agent_uses_github_models_provider(self, registry) -> None:
        """Integration point (b): model_provider is already free-form and
        needed no code change to accept a new provider value."""
        assert registry.agents["data-quality-agent"].model_provider == "github-models"

    def test_copilot_code_review_findings_can_be_framed_as_evidence(self, registry) -> None:
        """The github tool's copilot_code_review action description promises
        findings become Evidence(evidence_kind="review_record") -- proven
        constructible, never executed by this platform."""
        from domain.metamodel.base import EntityRef
        from domain.metamodel.entities.evaluation import Evidence
        from domain.metamodel.enums import EntityType, ProvenanceState

        evidence = Evidence(
            id="ev-copilot-1",
            name="Copilot review finding",
            entity_type=EntityType.EVIDENCE,
            evidence_kind="review_record",
            source_reference="https://github.com/example/repo/pull/1#pullrequestreview-1",
            subject_ref=EntityRef(type=EntityType.CODE_ARTIFACT, id="example"),
            provenance=ProvenanceState.OBSERVED,
            confidence=1.0,
            discovered_by="tool:github.copilot_code_review",
        )
        assert evidence.evidence_kind == "review_record"


class TestValidationFailures:
    """Broken marketplace catalog data fails loudly at load."""

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
        assert MetamodelRegistry.load(self._write(tmp_path / "ok"))

    def test_agent_with_unknown_role_key_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "bad-role",
            **{
                "agents.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    agents:
                      - key: ghost-agent
                        role_key: no-such-role
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="unknown engineering role 'no-such-role'"):
            MetamodelRegistry.load(root)

    def test_agent_with_unknown_skill_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "bad-skill",
            **{
                "agents.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    agents:
                      - key: ghost-agent
                        role_key: pipeline-engineer
                        skills: [no-such-skill]
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="unknown skill 'no-such-skill'"):
            MetamodelRegistry.load(root)

    def test_agent_with_unknown_tool_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "bad-tool",
            **{
                "agents.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    agents:
                      - key: ghost-agent
                        role_key: pipeline-engineer
                        tools: [no-such-tool]
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="unknown tool 'no-such-tool'"):
            MetamodelRegistry.load(root)

    def test_agent_with_unknown_knowledge_pack_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "bad-knowledge",
            **{
                "agents.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    agents:
                      - key: ghost-agent
                        role_key: pipeline-engineer
                        knowledge_packs: [no-such-pack]
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="unknown knowledge pack 'no-such-pack'"):
            MetamodelRegistry.load(root)

    def test_skill_requiring_unknown_tool_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "bad-skill-tool",
            **{
                "skills.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    skills:
                      - key: ghost-skill
                        required_tools: [no-such-tool]
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="ghost-skill.*unknown tool 'no-such-tool'"):
            MetamodelRegistry.load(root)

    def test_every_problem_reported_at_once(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "many",
            **{
                "agents.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    agents:
                      - key: ghost-agent
                        role_key: no-such-role
                        skills: [no-such-skill]
                        tools: [no-such-tool]
                    """
                )
            },
        )
        with pytest.raises(RegistryError) as exc:
            MetamodelRegistry.load(root)
        message = str(exc.value)
        assert "no-such-role" in message
        assert "no-such-skill" in message
        assert "no-such-tool" in message
