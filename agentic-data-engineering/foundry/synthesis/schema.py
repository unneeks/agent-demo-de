"""``candidate_content_schema_for()`` -- the JSON Schema an LLM must conform
to when proposing one candidate's content.

Reuses ``discovery.extraction.prompts.content_schema_for`` directly for the
structural stripping (base ``ProvenancedEntity`` fields, every
``EntityRef``-shaped field), then layers two Foundry-specific adjustments
-- deliberately not identical to how discovery itself uses that function:

* **Adds back ``name``/``description``** as required, LLM-authored
  fields. Discovery strips these because it auto-derives identity from a
  ``suggested_id``; Foundry deliberately wants the LLM's human-readable
  name and description, since that readability is the actual value
  synthesis adds over a deterministic field-copy.
* **Drops the entity's own ``<kind>_key`` field** (and, for ``Agent``
  only, the lifecycle fields ``status``/``certification_status``). The
  platform assigns candidate identity deterministically from the pattern
  that produced it -- mirroring discovery's own ``suggested_id`` -> real
  ``id`` trust boundary, the LLM never controls entity identity.
"""

from __future__ import annotations

from typing import Any

from discovery.extraction.prompts import content_schema_for
from domain.metamodel.enums import EntityType

#: The field the platform assigns deterministically for each candidate kind.
KEY_FIELD_BY_ENTITY_TYPE: dict[EntityType, str] = {
    EntityType.SKILL: "skill_key",
    EntityType.TOOL: "tool_key",
    EntityType.AGENT: "agent_key",
}

#: Fields every candidate kind loses beyond its own <kind>_key: `confidence`
#: is platform-assigned from the pattern's similarity_score (the LLM
#: authors content, never its own trust score -- the same "never a
#: literal the model invents" discipline `content_schema_for` already
#: applies to identity fields, extended to this one).
_UNIVERSAL_EXCLUDED_FIELDS: frozenset[str] = frozenset({"confidence"})

#: Lifecycle fields never LLM-authored, beyond the <kind>_key every entity
#: type already loses. Governance of a proposal lives on
#: CandidateReview.candidate_status, not on the embedded entity's own
#: lifecycle field.
_ADDITIONAL_EXCLUDED_FIELDS: dict[EntityType, frozenset[str]] = {
    EntityType.AGENT: frozenset({"status", "certification_status"}),
}

_NAME_DESCRIPTION_PROPERTIES: dict[str, Any] = {
    "name": {
        "type": "string",
        "minLength": 1,
        "maxLength": 512,
        "description": "A short, human-readable name for this proposal.",
    },
    "description": {
        "type": "string",
        "minLength": 1,
        "description": "A concise description of what this does and why, grounded in the "
        "recurring pattern it was synthesized from.",
    },
}


def candidate_content_schema_for(entity_type: EntityType) -> dict[str, Any]:
    if entity_type not in KEY_FIELD_BY_ENTITY_TYPE:
        raise ValueError(f"no candidate content schema for {entity_type.value!r}")

    schema = content_schema_for(entity_type)
    excluded = (
        {KEY_FIELD_BY_ENTITY_TYPE[entity_type]}
        | _UNIVERSAL_EXCLUDED_FIELDS
        | _ADDITIONAL_EXCLUDED_FIELDS.get(entity_type, frozenset())
    )

    properties = {
        key: value for key, value in schema["properties"].items() if key not in excluded
    }
    properties.update(_NAME_DESCRIPTION_PROPERTIES)

    required = sorted(
        {name for name in schema.get("required", []) if name not in excluded} | {"name", "description"}
    )

    result: dict[str, Any] = {
        **schema,
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    return result
