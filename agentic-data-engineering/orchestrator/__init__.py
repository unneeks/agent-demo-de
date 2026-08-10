"""The project orchestrator -- composes discovery, impact analysis,
composition and evaluation into one continuous cycle over a real project.

Every step calls an existing Phase 1-5 function; this package adds only the
write path those functions' own docs deferred (IMPLEMENTED_BY, Evaluation +
EVALUATES, the advanced Agent's status) and the two GateState assemblers
(passed_evaluations, traceability) that were always documented as
caller-supplied but never had a caller. See docs/orchestrator.md.
"""

from orchestrator.agent_step import AgentRunRequest, run_agents
from orchestrator.cycle import ObserveRequest, run_cycle
from orchestrator.errors import OrchestratorError, UnknownGateError
from orchestrator.evaluate import EvaluationRequest, run_evaluations
from orchestrator.gap_analysis import (
    GapAnalysisOutcome,
    GapAnalysisRequest,
    GapStaffingRecommendation,
    analyze_project_capability_gaps,
)
from orchestrator.gate import GateRequest, assemble_gate_state, assess_gate_readiness
from orchestrator.result import (
    AgentRunOutcome,
    CycleFailure,
    CycleReport,
    EvaluationOutcome,
    StaffingOutcome,
)
from orchestrator.staffing import engineering_roles_for_obligation, select_agents

__all__ = [
    "AgentRunOutcome",
    "AgentRunRequest",
    "CycleFailure",
    "CycleReport",
    "EvaluationOutcome",
    "EvaluationRequest",
    "GapAnalysisOutcome",
    "GapAnalysisRequest",
    "GapStaffingRecommendation",
    "GateRequest",
    "ObserveRequest",
    "OrchestratorError",
    "StaffingOutcome",
    "UnknownGateError",
    "analyze_project_capability_gaps",
    "assemble_gate_state",
    "assess_gate_readiness",
    "engineering_roles_for_obligation",
    "run_agents",
    "run_cycle",
    "run_evaluations",
    "select_agents",
]
