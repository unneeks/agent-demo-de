"""Shared fixtures and builders.

Builders exist so tests read as statements about behaviour rather than walls of
constructor arguments, and so adding a required field is a one-line fix here.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.metamodel.base import EntityRef, utc_now  # noqa: E402
from domain.metamodel.entities.evaluation import Evaluation  # noqa: E402
from domain.metamodel.entities.foundry import (  # noqa: E402
    CandidateAgent,
    CandidateReview,
    CandidateSkill,
    CandidateTool,
    EngineeringObservation,
    EngineeringPattern,
)
from domain.metamodel.entities.organization import Agent, Skill, Tool, ToolAction  # noqa: E402
from domain.metamodel.entities.shared.capability import (  # noqa: E402
    Capability,
    DeliveryCapability,
    Requirement,
)
from domain.metamodel.entities.shared.context import ContextItem, ContextPolicy  # noqa: E402
from domain.metamodel.entities.technical import (  # noqa: E402
    Change,
    CodeArtifact,
    DataAsset,
    Pipeline,
    Project,
    Test,
)
from domain.metamodel.enums import (  # noqa: E402
    ActionClass,
    ContextItemKind,
    EntityType,
    ProvenanceState,
    TestType,
    TrustLevel,
)
from domain.metamodel.registry import MetamodelRegistry  # noqa: E402
from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository  # noqa: E402

DISCOVERER = "test-fixture@0.1.0"


@pytest.fixture(scope="session")
def registry() -> MetamodelRegistry:
    """The real registries, loaded once and validated."""
    return MetamodelRegistry.load()


@pytest.fixture(scope="session")
def delivery_model(registry: MetamodelRegistry):
    """The worked data engineering delivery model."""
    model = registry.delivery_model("de-delivery-model")
    assert model is not None, "the worked delivery model must load"
    return model


@pytest.fixture
def graph() -> InMemoryGraphRepository:
    return InMemoryGraphRepository()


@pytest.fixture
def metadata() -> InMemoryMetadataRepository:
    return InMemoryMetadataRepository()


@pytest.fixture
def fixed_now() -> datetime:
    """A stable clock, so freshness and hash assertions do not flake."""
    return datetime.fromisoformat("2026-08-09T12:00:00+00:00")


def ref(entity_type: EntityType, entity_id: str, version: str | None = None) -> EntityRef:
    return EntityRef(type=entity_type, id=entity_id, version=version)


def _build(model: type, defaults: dict[str, object], overrides: dict[str, object]) -> object:
    """Construct ``model`` from defaults any caller may override.

    Merging rather than passing keywords twice is what lets a test say
    ``make_pipeline("x", provenance=INFERRED)`` without colliding with the
    builder's own default.
    """
    return model(**{**defaults, **overrides})


def _discovered(entity_type: EntityType, entity_id: str, **extra: object) -> dict[str, object]:
    return {
        "id": entity_id,
        "name": entity_id,
        "entity_type": entity_type,
        "provenance": ProvenanceState.OBSERVED,
        "discovered_by": DISCOVERER,
        **extra,
    }


def make_project(project_id: str = "demo", **kwargs: object) -> Project:
    return _build(Project, _discovered(EntityType.PROJECT, project_id), kwargs)  # type: ignore[return-value]


def make_pipeline(pipeline_id: str, project_id: str = "demo", **kwargs: object) -> Pipeline:
    return _build(  # type: ignore[return-value]
        Pipeline,
        _discovered(
            EntityType.PIPELINE,
            pipeline_id,
            project_ref=ref(EntityType.PROJECT, project_id),
            pipeline_kind="dbt_model",
        ),
        kwargs,
    )


def make_asset(asset_id: str, project_id: str = "demo", **kwargs: object) -> DataAsset:
    return _build(  # type: ignore[return-value]
        DataAsset,
        _discovered(
            EntityType.DATA_ASSET,
            asset_id,
            project_ref=ref(EntityType.PROJECT, project_id),
            asset_kind="table",
        ),
        kwargs,
    )


def make_code(code_id: str, project_id: str = "demo", **kwargs: object) -> CodeArtifact:
    return _build(  # type: ignore[return-value]
        CodeArtifact,
        _discovered(
            EntityType.CODE_ARTIFACT,
            code_id,
            project_ref=ref(EntityType.PROJECT, project_id),
            path=f"models/{code_id}",
        ),
        kwargs,
    )


def make_test(test_id: str, project_id: str = "demo", **kwargs: object) -> Test:
    return _build(  # type: ignore[return-value]
        Test,
        _discovered(
            EntityType.TEST,
            test_id,
            project_ref=ref(EntityType.PROJECT, project_id),
            test_type=TestType.REGRESSION,
        ),
        kwargs,
    )


def make_change(change_id: str = "PR-1", project_id: str = "demo", **kwargs: object) -> Change:
    return _build(  # type: ignore[return-value]
        Change,
        _discovered(
            EntityType.CHANGE,
            change_id,
            project_ref=ref(EntityType.PROJECT, project_id),
            change_kind="pull_request",
        ),
        kwargs,
    )


def make_requirement(requirement_id: str = "REQ-1", project_id: str = "demo", **kwargs: object) -> Requirement:
    return _build(  # type: ignore[return-value]
        Requirement,
        _discovered(
            EntityType.REQUIREMENT,
            requirement_id,
            project_ref=ref(EntityType.PROJECT, project_id),
            statement=f"Requirement {requirement_id}",
        ),
        kwargs,
    )


def make_agent(agent_id: str, role_key: str, **kwargs: object) -> Agent:
    return _build(  # type: ignore[return-value]
        Agent,
        {
            "id": agent_id,
            "name": agent_id,
            "entity_type": EntityType.AGENT,
            "agent_key": agent_id,
            "role_key": role_key,
        },
        kwargs,
    )


def make_skill(skill_id: str, **kwargs: object) -> Skill:
    return _build(  # type: ignore[return-value]
        Skill,
        {
            "id": skill_id,
            "name": skill_id,
            "entity_type": EntityType.SKILL,
            "skill_key": skill_id,
        },
        kwargs,
    )


def make_tool(tool_id: str, actions: list[ToolAction] | None = None, **kwargs: object) -> Tool:
    return _build(  # type: ignore[return-value]
        Tool,
        {
            "id": tool_id,
            "name": tool_id,
            "entity_type": EntityType.TOOL,
            "tool_key": tool_id,
            "actions": actions or [ToolAction(name="read", action_class=ActionClass.READ_ONLY)],
        },
        kwargs,
    )


def make_evaluation(
    evaluation_id: str = "eval-1",
    *,
    suite_key: str = "s",
    subject_ref: EntityRef,
    score: float = 1.0,
    delivery_score: float = 1.0,
    passed: bool = True,
    **kwargs: object,
) -> Evaluation:
    return _build(  # type: ignore[return-value]
        Evaluation,
        {
            "id": evaluation_id,
            "name": evaluation_id,
            "entity_type": EntityType.EVALUATION,
            "suite_ref": ref(EntityType.EVALUATION_SUITE, suite_key),
            "subject_ref": subject_ref,
            "score": score,
            "delivery_score": delivery_score,
            "passed": passed,
        },
        kwargs,
    )


def make_policy(
    policy_id: str = "default-context", *, max_tokens: int = 1000, **kwargs: object
) -> ContextPolicy:
    return _build(  # type: ignore[return-value]
        ContextPolicy,
        {
            "id": policy_id,
            "name": policy_id,
            "entity_type": EntityType.CONTEXT_POLICY,
            "policy_key": policy_id,
            "max_tokens": max_tokens,
        },
        kwargs,
    )


def make_capability(
    capability_key: str, project_id: str = "demo", *, maturity: int = 0, **kwargs: object
) -> Capability:
    return _build(  # type: ignore[return-value]
        Capability,
        _discovered(
            EntityType.CAPABILITY,
            f"{project_id}:{capability_key}",
            project_ref=ref(EntityType.PROJECT, project_id),
            capability_key=capability_key,
            maturity=maturity,
        ),
        kwargs,
    )


def make_delivery_capability(
    delivery_capability_key: str, project_id: str = "demo", *, maturity: int = 0, **kwargs: object
) -> DeliveryCapability:
    return _build(  # type: ignore[return-value]
        DeliveryCapability,
        _discovered(
            EntityType.DELIVERY_CAPABILITY,
            f"{project_id}:{delivery_capability_key}",
            project_ref=ref(EntityType.PROJECT, project_id),
            delivery_capability_key=delivery_capability_key,
            maturity=maturity,
        ),
        kwargs,
    )


def make_context_item(
    item_id: str,
    *,
    kind: ContextItemKind = ContextItemKind.KNOWLEDGE,
    priority: int = 0,
    trust: TrustLevel = TrustLevel.MEDIUM,
    tokens: int = 100,
    age_days: int = 0,
    now: datetime | None = None,
    content: str | None = None,
    citable: bool = True,
) -> ContextItem:
    reference = now or utc_now()
    return ContextItem(
        id=item_id,
        name=f"Item {item_id}",
        entity_type=EntityType.CONTEXT_ITEM,
        provenance=ProvenanceState.OBSERVED,
        discovered_by=DISCOVERER,
        kind=kind,
        priority=priority,
        trust_level=trust,
        token_estimate=tokens,
        as_of=reference - timedelta(days=age_days),
        content=content,
        content_reference=f"ref://{item_id}" if citable else None,
    )


def make_observation(
    observation_id: str, project_id: str = "demo", **kwargs: object
) -> EngineeringObservation:
    return _build(  # type: ignore[return-value]
        EngineeringObservation,
        _discovered(
            EntityType.ENGINEERING_OBSERVATION,
            observation_id,
            project_ref=ref(EntityType.PROJECT, project_id),
            source_ref=ref(EntityType.PIPELINE, "p1"),
            source_type="pipeline",
            activity="dbt_model",
        ),
        kwargs,
    )


def make_pattern(
    pattern_id: str,
    project_id: str = "demo",
    *,
    observation_refs: list[EntityRef] | None = None,
    **kwargs: object,
) -> EngineeringPattern:
    refs = observation_refs or [
        ref(EntityType.ENGINEERING_OBSERVATION, "o1"),
        ref(EntityType.ENGINEERING_OBSERVATION, "o2"),
    ]
    return _build(  # type: ignore[return-value]
        EngineeringPattern,
        {
            "id": pattern_id,
            "name": pattern_id,
            "entity_type": EntityType.ENGINEERING_PATTERN,
            "provenance": ProvenanceState.INFERRED,
            "confidence": 1.0,
            "discovered_by": DISCOVERER,
            "project_ref": ref(EntityType.PROJECT, project_id),
            "pattern_key": pattern_id,
            "category": "pipeline_shape",
            "observation_refs": refs,
            "frequency": len(refs),
            "common_activity": "dbt_model",
            "similarity_score": 1.0,
        },
        kwargs,
    )


def make_candidate_skill(
    candidate_id: str,
    *,
    proposed_key: str | None = None,
    pattern_refs: list[EntityRef] | None = None,
    proposed_skill: Skill | None = None,
    **kwargs: object,
) -> CandidateSkill:
    key = proposed_key or candidate_id
    refs = pattern_refs or [ref(EntityType.ENGINEERING_PATTERN, "pattern-1")]
    return _build(  # type: ignore[return-value]
        CandidateSkill,
        {
            "id": candidate_id,
            "name": candidate_id,
            "entity_type": EntityType.CANDIDATE_SKILL,
            "provenance": ProvenanceState.INFERRED,
            "confidence": 1.0,
            "discovered_by": DISCOVERER,
            "review": CandidateReview(
                proposed_key=key, derived_from_pattern_refs=refs, rationale="test rationale"
            ),
            "proposed_skill": proposed_skill or make_skill(key),
        },
        kwargs,
    )


def make_candidate_tool(
    candidate_id: str,
    *,
    proposed_key: str | None = None,
    pattern_refs: list[EntityRef] | None = None,
    proposed_tool: Tool | None = None,
    **kwargs: object,
) -> CandidateTool:
    key = proposed_key or candidate_id
    refs = pattern_refs or [ref(EntityType.ENGINEERING_PATTERN, "pattern-1")]
    return _build(  # type: ignore[return-value]
        CandidateTool,
        {
            "id": candidate_id,
            "name": candidate_id,
            "entity_type": EntityType.CANDIDATE_TOOL,
            "provenance": ProvenanceState.INFERRED,
            "confidence": 1.0,
            "discovered_by": DISCOVERER,
            "review": CandidateReview(
                proposed_key=key, derived_from_pattern_refs=refs, rationale="test rationale"
            ),
            "proposed_tool": proposed_tool or make_tool(key),
        },
        kwargs,
    )


def make_candidate_agent(
    candidate_id: str,
    *,
    proposed_key: str | None = None,
    pattern_refs: list[EntityRef] | None = None,
    proposed_agent: Agent | None = None,
    role_key: str = "data-model-engineer",
    **kwargs: object,
) -> CandidateAgent:
    key = proposed_key or candidate_id
    refs = pattern_refs or [ref(EntityType.ENGINEERING_PATTERN, "pattern-1")]
    return _build(  # type: ignore[return-value]
        CandidateAgent,
        {
            "id": candidate_id,
            "name": candidate_id,
            "entity_type": EntityType.CANDIDATE_AGENT,
            "provenance": ProvenanceState.INFERRED,
            "confidence": 1.0,
            "discovered_by": DISCOVERER,
            "review": CandidateReview(
                proposed_key=key, derived_from_pattern_refs=refs, rationale="test rationale"
            ),
            "proposed_agent": proposed_agent or make_agent(key, role_key),
        },
        kwargs,
    )
