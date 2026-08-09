"""Marketplace resolution: matching catalog agents against engineering roles.

Every assertion here treats EngineeringRole.is_satisfied_by()/
missing_requirements() as ground truth -- the engine is proven to be a wrapper
around that logic, not a new definition of what "satisfies" means.
"""

from __future__ import annotations

from domain.metamodel.enums import EntityType
from engines.composition import assess_candidate, resolve_catalog, resolve_role

from tests.conftest import make_agent


class TestAssessCandidate:
    def test_agrees_with_is_satisfied_by_for_a_real_match(self, registry) -> None:
        role = registry.engineering_roles["regression-engineer"]
        agent = registry.agents["regression-agent"]
        assessment = assess_candidate(role, agent)
        expected = role.is_satisfied_by(
            capabilities=set(agent.capabilities),
            delivery_capabilities=set(agent.delivery_capabilities),
            skills=set(agent.skills),
            tools=set(agent.tools),
            knowledge=set(agent.knowledge_packs),
        )
        assert assessment.satisfies is expected is True
        assert assessment.coverage == 1.0
        assert assessment.missing == {
            "capabilities": [],
            "delivery_capabilities": [],
            "skills": [],
            "tools": [],
            "knowledge": [],
        }

    def test_agrees_with_missing_requirements_for_a_near_miss(self, registry) -> None:
        role = registry.engineering_roles["regression-engineer"]
        agent = registry.agents["copilot-coding-agent-regression"]
        assessment = assess_candidate(role, agent)
        expected_missing = role.missing_requirements(
            capabilities=set(agent.capabilities),
            delivery_capabilities=set(agent.delivery_capabilities),
            skills=set(agent.skills),
            tools=set(agent.tools),
            knowledge=set(agent.knowledge_packs),
        )
        assert not assessment.satisfies
        assert assessment.missing == expected_missing
        assert 0.0 < assessment.coverage < 1.0

    def test_explain_names_the_gaps_for_a_near_miss(self, registry) -> None:
        role = registry.engineering_roles["regression-engineer"]
        agent = registry.agents["copilot-coding-agent-regression"]
        explanation = assess_candidate(role, agent).explain()
        assert "does not satisfy" in explanation
        assert "skills:" in explanation

    def test_explain_for_a_match(self, registry) -> None:
        role = registry.engineering_roles["regression-engineer"]
        agent = registry.agents["regression-agent"]
        assert assess_candidate(role, agent).explain() == "regression-agent satisfies regression-engineer"


class TestResolveRole:
    def test_partitions_matches_and_near_misses(self, registry) -> None:
        role = registry.engineering_roles["regression-engineer"]
        candidates = [registry.agents["regression-agent"], registry.agents["copilot-coding-agent-regression"]]
        resolution = resolve_role(role, candidates)
        assert [m.agent_key for m in resolution.matches] == ["regression-agent"]
        assert [m.agent_key for m in resolution.near_misses] == ["copilot-coding-agent-regression"]
        assert resolution.is_staffable
        assert resolution.best_match.agent_key == "regression-agent"

    def test_filters_by_declared_role_by_default(self, registry) -> None:
        role = registry.engineering_roles["regression-engineer"]
        off_role_twin = make_agent(
            "off-role-twin",
            role_key="impact-analysis-engineer",
            capabilities=["regression-testing", "impact-analysis", "testing"],
            delivery_capabilities=["regression-assurance"],
            skills=["repository-discovery", "dependency-analysis", "impact-analysis", "test-selection", "test-execution"],
            tools=["git", "github", "pytest"],
            knowledge_packs=["project-architecture", "testing-standards"],
        )
        resolution = resolve_role(role, [off_role_twin])
        assert resolution.matches == []
        assert resolution.near_misses == []

    def test_strict_role_match_false_widens_the_search(self, registry) -> None:
        role = registry.engineering_roles["regression-engineer"]
        off_role_twin = make_agent(
            "off-role-twin",
            role_key="impact-analysis-engineer",
            capabilities=["regression-testing", "impact-analysis", "testing"],
            delivery_capabilities=["regression-assurance"],
            skills=["repository-discovery", "dependency-analysis", "impact-analysis", "test-selection", "test-execution"],
            tools=["git", "github", "pytest"],
            knowledge_packs=["project-architecture", "testing-standards"],
        )
        resolution = resolve_role(role, [off_role_twin], strict_role_match=False)
        assert [m.agent_key for m in resolution.matches] == ["off-role-twin"]

    def test_ranking_is_deterministic_by_coverage_then_agent_key(self, registry) -> None:
        role = registry.engineering_roles["regression-engineer"]
        low_coverage = make_agent(
            "z-low-coverage", role_key="regression-engineer", capabilities=["regression-testing"]
        )
        higher_coverage = make_agent(
            "a-higher-coverage",
            role_key="regression-engineer",
            capabilities=["regression-testing", "impact-analysis"],
        )
        resolution = resolve_role(role, [low_coverage, higher_coverage])
        assert [a.agent_key for a in resolution.near_misses] == [
            "a-higher-coverage",
            "z-low-coverage",
        ]

    def test_equal_coverage_breaks_tie_alphabetically(self, registry) -> None:
        role = registry.engineering_roles["regression-engineer"]
        agent_b = make_agent("b-agent", role_key="regression-engineer")
        agent_a = make_agent("a-agent", role_key="regression-engineer")
        resolution = resolve_role(role, [agent_b, agent_a])
        assert [a.agent_key for a in resolution.near_misses] == ["a-agent", "b-agent"]


class TestResolveCatalog:
    def test_covers_every_engineering_role(self, registry) -> None:
        resolutions = resolve_catalog(registry)
        assert set(resolutions) == set(registry.engineering_roles)

    def test_five_staffed_roles_are_staffable(self, registry) -> None:
        resolutions = resolve_catalog(registry)
        for role_key in (
            "regression-engineer",
            "impact-analysis-engineer",
            "data-quality-engineer",
            "data-model-engineer",
            "delivery-compliance-engineer",
        ):
            assert resolutions[role_key].is_staffable, role_key

    def test_unstaffed_roles_have_no_matches(self, registry) -> None:
        resolutions = resolve_catalog(registry)
        assert resolutions["security-engineer"].matches == []
