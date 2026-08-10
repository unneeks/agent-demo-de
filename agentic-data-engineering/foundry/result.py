"""The shapes ``foundry/run.py`` produces.

``FoundryCycleFailure`` mirrors ``discovery.result.DiscoveryFailure``'s own
"a write/synthesis that was attempted and rejected, never partially
applied" shape -- a synthesis failure (schema violation, LLM transport
error) for one pattern/kind is recorded here and does not abort the rest
of the run under ``on_error="collect"``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.foundry import (
    CandidateAgent,
    CandidateSkill,
    CandidateTool,
    EngineeringObservation,
    EngineeringPattern,
)
from domain.metamodel.entities.evaluation import Evaluation


@dataclass(frozen=True)
class FoundryCycleFailure:
    """A synthesis or evaluation step that was attempted and rejected."""

    kind: str
    detail: str
    source: str


@dataclass(frozen=True)
class FoundryCycleReport:
    """The outcome of one full ``run_foundry_cycle()`` run."""

    project_ref: EntityRef
    observations: list[EngineeringObservation] = field(default_factory=list)
    patterns: list[EngineeringPattern] = field(default_factory=list)
    candidate_skills: list[CandidateSkill] = field(default_factory=list)
    candidate_tools: list[CandidateTool] = field(default_factory=list)
    candidate_agents: list[CandidateAgent] = field(default_factory=list)
    evaluations: list[Evaluation] = field(default_factory=list)
    failed: list[FoundryCycleFailure] = field(default_factory=list)
