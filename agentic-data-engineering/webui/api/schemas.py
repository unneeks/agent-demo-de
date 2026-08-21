"""Request/response shapes for `/api/*`.

Real domain entities (`Project`, `Relationship`, `Evaluation`,
`GateReadiness`, `ChecklistOutcome`, `ContextPolicy`, `Change`,
`EntityRef`) are used directly as request/response fields wherever
possible -- never re-derived. A shape is hand-written here only where the
HTML route it mirrors already builds an ad hoc dict for its template,
never where a real entity would do.

`entities_by_type`/`phases`/`checklists`/`staffing` use `dict`/`list[dict]`
rather than a hand-maintained discriminated union of every one of the 68
`ENTITY_CLASSES` members -- a deliberate, stated judgment call (the
smallest correct thing, matching exactly what the HTML route already
builds) over a more elaborate union nobody asked for.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.delivery import ApprovalGate, DeliveryModel
from domain.metamodel.entities.shared.context import ContextPolicy
from domain.metamodel.entities.technical import Change
from domain.metamodel.enums import AgentLifecycle, ApprovalLevel, AutomationLevel, EntityType
from domain.metamodel.relationships import Relationship
from engines.gates import ChecklistOutcome


class ProjectGraphResponse(BaseModel):
    project_id: str
    entities_by_type: dict[EntityType, list[dict]]
    relationships_by_type: dict[str, list[Relationship]]
    catalog_reference_count: int


class DeliveryModelSummary(BaseModel):
    key: str
    name: str
    methodology: str | None


class DeliveryModelDetailResponse(BaseModel):
    model_key: str
    model: DeliveryModel
    phases: list[dict]
    checklists: list[dict]
    gates: list[ApprovalGate]


class MarketplaceResponse(BaseModel):
    agents: list[dict]
    skills: list[dict]
    tools: list[dict]
    knowledge_packs: list[dict]
    staffing: list[dict]


class EvaluationRunRequest(BaseModel):
    suite_key: str
    subject_ref: EntityRef
    observed_values: dict[str, float]
    evidence_refs: list[EntityRef] | None = None
    component_versions: dict[str, str] | None = None
    evaluated_at: datetime | None = None
    #: Resolved server-side to the real `registry.agents[...]` object --
    #: never accepted as a client-supplied Agent payload.
    advance_agent_key: str | None = None
    advance_to: AgentLifecycle | None = None


class GateAssessRequest(BaseModel):
    present_artifact_kinds: set[str] = set()
    checklist_outcomes: dict[str, ChecklistOutcome] = {}
    satisfied_evidence: set[str] = set()
    approvals: set[str] = set()
    evaluation_subject_ref: EntityRef | None = None


class GateAssessKeyedRequest(GateAssessRequest):
    gate_key: str


class AgentRunHttpRequest(BaseModel):
    agent_key: str
    task: str
    max_iterations: int | None = None
    #: The only three backends this codebase ships -- see
    #: agent_runtime/{replay_client,anthropic_client,copilot_cli_client}.py.
    #: tool_executor is never a request field: every run always uses
    #: SimulatedToolExecutor, server-side, non-configurable.
    llm_backend: Literal["replay", "anthropic", "copilot_cli"]
    automation_level: AutomationLevel
    granted_approval: ApprovalLevel = ApprovalLevel.NONE
    #: Required, not defaulted server-side -- there is no canonical default
    #: ContextPolicy anywhere in this codebase, and inventing one would
    #: silently constrain every caller. "Never a literal."
    context_policy: ContextPolicy


class CycleRunRequest(BaseModel):
    delivery_model_key: str
    change: Change | None = None
    change_seeds: list[EntityRef] | None = None
    max_depth: int = 5
    min_confidence: float = 0.0
    agent_run_requests: list[AgentRunHttpRequest] = []
    evaluation_requests: list[EvaluationRunRequest] = []
    gates: list[GateAssessKeyedRequest] = []
    on_error: Literal["fail_fast", "collect"] = "collect"


__all__ = [
    "AgentRunHttpRequest",
    "CycleRunRequest",
    "DeliveryModelDetailResponse",
    "DeliveryModelSummary",
    "EvaluationRunRequest",
    "GateAssessKeyedRequest",
    "GateAssessRequest",
    "MarketplaceResponse",
    "ProjectGraphResponse",
]
