"""Gating `Agent` lifecycle transitions on a passing, subject-matching
`Evaluation`.

A thin wrapper around `Agent.transition_to()`
(`domain/metamodel/entities/organization/agents.py`) -- the structural
legality of a transition (`AGENT_LIFECYCLE_TRANSITIONS`) stays exactly where
it is; this module adds only the evaluation precondition `transition_to()`
has no way to know about, the same "orchestration wraps, entities stay
structural" split ADR-0011 used for `ProjectGraphService` over the graph
repositories.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from domain.metamodel.base import EntityRef, MetamodelModel, utc_now
from domain.metamodel.entities.evaluation import Evaluation
from domain.metamodel.entities.organization import Agent
from domain.metamodel.enums import AgentLifecycle, EntityType

#: Transitions that require a passing, subject-matching Evaluation. Every
#: other legal transition (DRAFT->CANDIDATE, CANDIDATE->DRAFT/RETIRED,
#: EVALUATED->CANDIDATE/RETIRED, CERTIFIED->DEPLOYED/DEPRECATED, ...) needs
#: none -- an evaluation proves fitness, it is not required to retreat,
#: retire, deploy (Deployment's own citation check is a different layer), or
#: flag for re-evaluation (which would be circular).
GATED_TRANSITIONS: frozenset[AgentLifecycle] = frozenset(
    {AgentLifecycle.EVALUATED, AgentLifecycle.CERTIFIED}
)


class AgentAdvancement(MetamodelModel):
    """Audit record of one gated (or ungated) lifecycle move."""

    agent_key: str
    from_status: AgentLifecycle
    to_status: AgentLifecycle
    evaluation_ref: EntityRef | None = None
    advanced_at: datetime = Field(default_factory=utc_now)


def advance_agent(
    agent: Agent,
    target: AgentLifecycle,
    *,
    evaluation: Evaluation | None = None,
    now: datetime | None = None,
) -> AgentAdvancement:
    """Move `agent` to `target`, requiring a passing evaluation for gated targets.

    Mutates `agent` in place (matching `Agent.transition_to()`'s own
    mutate-and-return-None style) and returns an audit record. The evaluation
    precondition is checked before calling `transition_to()`, so a rejected
    precondition never leaves the agent partially transitioned. The
    underlying structural check (`AGENT_LIFECYCLE_TRANSITIONS`) still applies
    unmodified -- this function adds a precondition, it never weakens one.
    """
    if target in GATED_TRANSITIONS:
        if evaluation is None:
            raise ValueError(
                f"agent {agent.agent_key!r} cannot advance to {target.value} without a "
                "passing Evaluation"
            )
        if evaluation.subject_ref.type is not EntityType.AGENT or (
            evaluation.subject_ref.id != agent.agent_key
        ):
            raise ValueError(
                f"evaluation {evaluation.id!r} does not evaluate agent {agent.agent_key!r} "
                f"(subject_ref={evaluation.subject_ref})"
            )
        if not evaluation.passed:
            raise ValueError(
                f"evaluation {evaluation.id!r} for agent {agent.agent_key!r} did not pass; "
                f"cannot advance to {target.value}"
            )

    from_status = agent.status
    agent.transition_to(target)

    return AgentAdvancement(
        agent_key=agent.agent_key,
        from_status=from_status,
        to_status=target,
        evaluation_ref=evaluation.ref(pinned=True) if evaluation is not None else None,
        advanced_at=now or utc_now(),
    )
