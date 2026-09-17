"""The shapes `run_cycle` reports through -- itemized, never a boolean.

Mirrors `discovery.result`'s `DiscoveryReport`/`DiscoveryFailure` shapes: a
`CycleFailure` is a soft, per-step outcome collected so the rest of a cycle
can continue (`on_error="collect"`, the default), never a silent drop.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.evaluation import Evaluation
from agent_runtime.result import AgentRunReport
from discovery.result import DiscoveryReport
from engines.composition import RoleResolution
from engines.evaluation import AgentAdvancement
from engines.gates import GateReadiness
from engines.impact import ChangeImpact
from orchestrator.gap_analysis import GapAnalysisOutcome


@dataclass(frozen=True)
class StaffingOutcome:
    """One (obligation, engineering role) resolution attempt.

    A first-class, reportable outcome even when nothing could be staffed --
    an obligation whose responsibility names no engineering role at all
    (`resp.architecture-signoff`), or an engineering role with zero
    candidate agents (`data-architect`), is real registry data, not an
    error.
    """

    obligation_kind: str
    obligation_key: str
    delivery_role_key: str
    responsibility_key: str | None
    engineering_role_key: str | None
    resolution: RoleResolution | None
    staffed_agent_key: str | None
    implemented_by_written: bool


@dataclass(frozen=True)
class EvaluationOutcome:
    """One evaluation run, and the lifecycle advancement it drove, if any."""

    suite_key: str
    subject_ref: EntityRef
    evaluation: Evaluation
    advancement: AgentAdvancement | None


@dataclass(frozen=True)
class AgentRunOutcome:
    """One agent actually run, linked back to the staffing decision (if
    any) that named it. An agent run's rich output is deliberately not
    auto-translated into an EvaluationRequest -- see docs/orchestrator.md
    and docs/agent-runtime.md. AgentRunReport.evidence is the bridge a
    caller can hand-wire into evaluation_requests, exactly as
    EvaluationRequest.observed_values already stays plain caller input."""

    agent_key: str
    task: str
    report: AgentRunReport
    staffing_outcome: StaffingOutcome | None = None


@dataclass(frozen=True)
class CycleFailure:
    """A step that was attempted and rejected -- never partially applied."""

    kind: str
    detail: str
    source: str


@dataclass(frozen=True)
class CycleReport:
    """The outcome of one full `run_cycle` run."""

    project_ref: EntityRef
    discovery: DiscoveryReport | None = None
    impact: ChangeImpact | None = None
    staffing: list[StaffingOutcome] = field(default_factory=list)
    agent_runs: list[AgentRunOutcome] = field(default_factory=list)
    evaluations: list[EvaluationOutcome] = field(default_factory=list)
    gate_readiness: dict[str, GateReadiness] = field(default_factory=dict)
    gap_analysis: GapAnalysisOutcome | None = None
    failed: list[CycleFailure] = field(default_factory=list)
