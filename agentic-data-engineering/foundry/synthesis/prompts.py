"""``build_candidate_prompt()`` -- the prompt + response schema for one
candidate-content synthesis call.

Reuses ``discovery.extraction.prompts.ExtractionPrompt`` directly (the
real ``prompt: str, response_schema: dict`` dataclass) -- no parallel
container type.
"""

from __future__ import annotations

from discovery.extraction.prompts import ExtractionPrompt
from domain.metamodel.entities.foundry import EngineeringObservation, EngineeringPattern
from domain.metamodel.enums import EntityType
from foundry.synthesis.schema import candidate_content_schema_for

_KIND_LABEL: dict[EntityType, str] = {
    EntityType.SKILL: "Skill",
    EntityType.TOOL: "Tool",
    EntityType.AGENT: "Agent",
}

#: Bounds prompt size against a pattern with an unusually large number of
#: grouped observations -- the digest is grounding context, not a complete
#: record (every observation is already reachable via the pattern's
#: observation_refs for anyone who needs the full list).
MAX_OBSERVATIONS_IN_DIGEST = 10


def _observation_digest(observations: list[EngineeringObservation]) -> str:
    shown = observations[:MAX_OBSERVATIONS_IN_DIGEST]
    lines = []
    for observation in shown:
        actor = f", actor={observation.actor}" if observation.actor else ""
        outcome = f", outcome={observation.outcome}" if observation.outcome else ""
        lines.append(
            f"- {observation.source_type}: {observation.activity} "
            f"(inputs={observation.inputs}, outputs={observation.outputs}{actor}{outcome})"
        )
    if len(observations) > MAX_OBSERVATIONS_IN_DIGEST:
        lines.append(f"- ... and {len(observations) - MAX_OBSERVATIONS_IN_DIGEST} more")
    return "\n".join(lines) if lines else "(no individual observations supplied)"


def build_candidate_prompt(
    pattern: EngineeringPattern,
    observations: list[EngineeringObservation],
    entity_type: EntityType,
) -> ExtractionPrompt:
    kind = _KIND_LABEL[entity_type]
    variations_line = f"Known variations: {pattern.known_variations}\n" if pattern.known_variations else ""
    prompt = (
        f"You are proposing a reusable marketplace {kind} for a data engineering "
        f"platform, distilled from a recurring pattern found in an existing project's "
        f"already-ingested graph. Everything you propose is treated as INFERRED, never "
        f"as certain -- report a grounded, honest name and description; do not invent "
        f"capabilities the pattern does not support.\n\n"
        f"Pattern category: {pattern.category}\n"
        f"Recurring activity: {pattern.common_activity}\n"
        f"Technology: {pattern.common_technology or '(none recorded)'}\n"
        f"Observed {pattern.frequency} times, similarity score "
        f"{pattern.similarity_score:.2f} (1.0 = identical inputs/outputs across every "
        f"occurrence).\n"
        f"Common inputs: {pattern.common_inputs or '(none)'}\n"
        f"Common outputs: {pattern.common_outputs or '(none)'}\n"
        f"{variations_line}"
        f"\nUnderlying observations:\n{_observation_digest(observations)}\n\n"
        f"Propose a {kind} that generalizes this recurring pattern into a reusable "
        f"marketplace capability. Where the schema calls for input/output fields, "
        f"populate them to reflect the pattern's common inputs/outputs."
    )
    return ExtractionPrompt(prompt=prompt, response_schema=candidate_content_schema_for(entity_type))
