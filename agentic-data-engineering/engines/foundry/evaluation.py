"""``score_candidate_completeness()`` -- structural/contract-completeness
scoring for an unpublished marketplace candidate.

Pure: no I/O, no LLM. Deliberately **not** historical replay: this
codebase has no benchmark corpus or execution sandbox to replay a
candidate against, so scoring stays honestly narrow -- proxy metrics over
the candidate's own declared shape -- rather than inventing
historical-performance numbers. The real, unmodified
``engines/evaluation/harness.py::run_suite()`` does the actual scoring
against these observed values; this module only produces them.
"""

from __future__ import annotations

from domain.metamodel.entities.foundry import (
    CandidateAgent,
    CandidateSkill,
    CandidateTool,
    EngineeringPattern,
)

Candidate = CandidateSkill | CandidateTool | CandidateAgent


def _io_contract_completeness(candidate: Candidate) -> float:
    if isinstance(candidate, CandidateSkill):
        payload = candidate.proposed_skill
        return 1.0 if payload.inputs and payload.outputs else 0.0
    if isinstance(candidate, CandidateAgent):
        payload = candidate.proposed_agent
        return 1.0 if payload.inputs and payload.outputs else 0.0
    # CandidateTool: a Tool has no inputs/outputs of its own -- its I/O
    # contract lives on its actions' input_schema/output_schema instead.
    actions = candidate.proposed_tool.actions
    has_schema = any(action.input_schema or action.output_schema for action in actions)
    return 1.0 if actions and has_schema else 0.0


def _checklist_traceability(candidate: Candidate) -> float:
    if isinstance(candidate, CandidateSkill):
        return 1.0 if candidate.proposed_skill.discharges_checklist_items else 0.0
    # Not a meaningful concept for Tool/Agent candidates; the suites for
    # those kinds do not reference this metric, so the value is unused.
    return 0.0


def _pattern_support(pattern: EngineeringPattern) -> float:
    return min(1.0, pattern.frequency / 5)


def score_candidate_completeness(candidate: Candidate, pattern: EngineeringPattern) -> dict[str, float]:
    """The ``observed_values`` dict ``run_suite()`` needs, purely from the
    candidate's own structural fields and the pattern that produced it.
    """
    return {
        "candidate-io-contract-completeness": _io_contract_completeness(candidate),
        "candidate-checklist-traceability": _checklist_traceability(candidate),
        "candidate-pattern-support": _pattern_support(pattern),
    }
