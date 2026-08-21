"""The evaluation catalog: evaluation_metrics/scenarios/suites registries.

Loading, cross-registry referential integrity, and the direct proof that the
worked catalog is real -- `architecture-quality-evaluation` is exactly the
suite key `gate.architecture-review` has always named but never had defined,
and `regression-agent-certification`'s passing thresholds are the role's own
numbers, not arbitrary ones. See ADR-0015.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from domain.metamodel.registry import MetamodelRegistry, RegistryError
from domain.metamodel.version import METAMODEL_VERSION


class TestLoading:
    def test_catalogs_load_non_empty(self, registry) -> None:
        assert registry.evaluation_metrics
        assert registry.evaluation_scenarios
        assert registry.evaluation_suites


class TestReferentialIntegrity:
    def test_every_suite_scenario_and_metric_ref_resolves(self, registry) -> None:
        for key, suite in registry.evaluation_suites.items():
            for ref_ in suite.scenario_refs:
                assert ref_.id in registry.evaluation_scenarios, (key, ref_.id)
            for ref_ in suite.metric_refs:
                assert ref_.id in registry.evaluation_metrics, (key, ref_.id)

    def test_every_scenario_metric_key_resolves(self, registry) -> None:
        for key, scenario in registry.evaluation_scenarios.items():
            for metric_key in scenario.metric_keys:
                assert metric_key in registry.evaluation_metrics, (key, metric_key)


class TestWorkedCatalogIsReal:
    def test_architecture_gate_evaluation_reference_is_closed(self, registry) -> None:
        gate = registry.delivery_models["de-delivery-model"].gates["gate.architecture-review"]
        [suite_ref] = gate.required_evaluation_refs
        assert suite_ref.id == "architecture-quality-evaluation"
        assert suite_ref.id in registry.evaluation_suites

    def test_architecture_suite_is_workflow_level(self, registry) -> None:
        assert registry.evaluation_suites["architecture-quality-evaluation"].level == "workflow"

    def test_regression_certification_thresholds_match_the_role(self, registry) -> None:
        suite = registry.evaluation_suites["regression-agent-certification"]
        role = registry.engineering_roles["regression-engineer"]
        assert suite.passing_score == role.minimum_evaluation_score
        assert suite.passing_delivery_score == role.minimum_delivery_conformance

    def test_regression_certification_is_agent_level(self, registry) -> None:
        assert registry.evaluation_suites["regression-agent-certification"].level == "agent"


class TestValidationFailures:
    """Broken evaluation catalog data fails loudly at load."""

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

    def test_suite_with_unknown_scenario_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "bad-scenario",
            **{
                "evaluation_suites.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    evaluation_suites:
                      - key: ghost-suite
                        level: agent
                        scenarios: [no-such-scenario]
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="unknown scenario 'no-such-scenario'"):
            MetamodelRegistry.load(root)

    def test_suite_with_unknown_metric_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "bad-metric",
            **{
                "evaluation_suites.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    evaluation_suites:
                      - key: ghost-suite
                        level: agent
                        metrics: [no-such-metric]
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="unknown metric 'no-such-metric'"):
            MetamodelRegistry.load(root)

    def test_scenario_with_unknown_metric_key_is_rejected(self, tmp_path: Path) -> None:
        root = self._write(
            tmp_path / "bad-scenario-metric",
            **{
                "evaluation_scenarios.yaml": textwrap.dedent(
                    """
                    version: 0.1.0
                    evaluation_scenarios:
                      - key: ghost-scenario
                        metric_keys: [no-such-metric]
                    """
                )
            },
        )
        with pytest.raises(RegistryError, match="unknown metric 'no-such-metric'"):
            MetamodelRegistry.load(root)

    def test_gate_naming_an_unknown_evaluation_suite_is_rejected(self, tmp_path: Path) -> None:
        delivery_models_dir = tmp_path / "bad-gate-eval" / "delivery-models"
        root = self._write(tmp_path / "bad-gate-eval")
        delivery_models_dir.mkdir(parents=True, exist_ok=True)
        (delivery_models_dir / "minimal.yaml").write_text(
            textwrap.dedent(
                """
                model:
                  key: minimal-model
                gates:
                  - key: gate.ghost
                    name: Ghost Gate
                    phases: []
                    required_evaluations: [no-such-suite]
                """
            ),
            encoding="utf-8",
        )
        with pytest.raises(RegistryError, match="unknown evaluation suite 'no-such-suite'"):
            MetamodelRegistry.load(root)
