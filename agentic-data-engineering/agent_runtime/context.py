"""Building an agent's system prompt from its registry-declared skills and
knowledge packs -- the first real caller of `engines.context.assembler.
assemble()` (zero callers outside its own test suite through Phase 6).

Skill/KnowledgePack items are mapped to `ContextItemKind.KNOWLEDGE`: an
honest fit for "what the agent needs to know to act", not a metamodel gap --
`ContextItemKind` has no dedicated "skill instructions" kind, and widening
the enum for something an existing value already covers would contradict
ADR-0006's own minimalism. `assemble()` itself is used unmodified; this
module only adds the one step it deliberately stops short of: turning a
`ContextBundle` into the text a model actually sees.
"""

from __future__ import annotations

from datetime import datetime

from domain.metamodel.base import utc_now
from domain.metamodel.entities.organization import Agent
from domain.metamodel.entities.shared.context import ContextBundle, ContextItem, ContextPolicy
from domain.metamodel.enums import ContextItemKind, ProvenanceState, TrustLevel
from domain.metamodel.registry import MetamodelRegistry
from engines.context.assembler import assemble
from engines.context.budget import DEFAULT_ESTIMATOR, TokenEstimator

_DISCOVERED_BY = "agent_runtime@0.1.0"


def _knowledge_pack_item(pack_key: str, registry: MetamodelRegistry, now: datetime) -> ContextItem | None:
    pack = registry.knowledge_packs.get(pack_key)
    if pack is None:
        return None
    content = pack.description or pack.name
    return ContextItem(
        id=f"knowledge-pack:{pack.knowledge_key}",
        name=pack.name,
        entity_type=ContextItem.model_fields["entity_type"].default,
        provenance=ProvenanceState.OBSERVED,
        discovered_by=_DISCOVERED_BY,
        kind=ContextItemKind.KNOWLEDGE,
        content=content,
        content_reference=pack.content_reference,
        token_estimate=DEFAULT_ESTIMATOR.estimate(content),
        trust_level=pack.trust_level,
        as_of=now,
    )


def _skill_item(skill_key: str, registry: MetamodelRegistry, now: datetime) -> ContextItem | None:
    skill = registry.skills.get(skill_key)
    if skill is None:
        return None
    lines = [skill.description or skill.name]
    if skill.preconditions:
        lines.append("Preconditions: " + "; ".join(skill.preconditions))
    if skill.postconditions:
        lines.append("Postconditions: " + "; ".join(skill.postconditions))
    content = "\n".join(lines)
    return ContextItem(
        id=f"skill:{skill.skill_key}",
        name=skill.name,
        entity_type=ContextItem.model_fields["entity_type"].default,
        provenance=ProvenanceState.OBSERVED,
        discovered_by=_DISCOVERED_BY,
        kind=ContextItemKind.KNOWLEDGE,
        content=content,
        content_reference=f"skill://{skill.skill_key}",
        token_estimate=DEFAULT_ESTIMATOR.estimate(content),
        trust_level=TrustLevel.HIGH,
        as_of=now,
    )


def build_agent_context(
    agent: Agent,
    registry: MetamodelRegistry,
    task: str,
    *,
    policy: ContextPolicy,
    extra_candidates: list[ContextItem] | None = None,
    estimator: TokenEstimator | None = None,
    now: datetime | None = None,
) -> ContextBundle:
    """Assemble the context bundle an agent's run will be shown, from its
    declared knowledge_packs and skills plus any caller-supplied extras
    (e.g. delivery-control items). `task` is not itself a candidate -- it is
    rendered separately by `render_system_prompt`."""
    reference_time = now or utc_now()
    candidates: list[ContextItem] = []
    for pack_key in agent.knowledge_packs:
        item = _knowledge_pack_item(pack_key, registry, reference_time)
        if item is not None:
            candidates.append(item)
    for skill_key in agent.skills:
        item = _skill_item(skill_key, registry, reference_time)
        if item is not None:
            candidates.append(item)
    candidates.extend(extra_candidates or [])

    return assemble(
        policy,
        candidates,
        estimator=estimator,
        agent_ref=agent.ref(),
        now=reference_time,
    )


def render_system_prompt(bundle: ContextBundle, agent: Agent, task: str) -> str:
    """Bundle -> text. `assemble()` deliberately stops at 'what the agent
    will see' as structured items, not a rendered string -- this supplies
    the missing last step."""
    sections = [
        f"You are {agent.name}. {agent.mission or ''}".strip(),
        f"Task: {task}",
    ]
    if bundle.items:
        sections.append("Context:")
        for item in bundle.items:
            sections.append(f"- [{item.kind.value}] {item.name}: {item.content or item.content_reference}")
    return "\n\n".join(sections)


__all__ = ["build_agent_context", "render_system_prompt"]
