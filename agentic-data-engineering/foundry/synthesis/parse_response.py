"""``parse_candidate_content()`` -- turns one raw ``ExtractionClient``
response into a real ``Skill``/``Tool``/``Agent``.

The same two-layer defense ``discovery/extraction/parse_response.py``
already established: ``jsonschema.validate`` against the exact schema the
client was asked to conform to first (a non-conforming response is
rejected wholesale, never partially trusted), then Pydantic construction
of the real entity, enforcing every metamodel invariant regardless of what
the LLM actually returned.
"""

from __future__ import annotations

from typing import Any

import jsonschema
from pydantic import ValidationError

from discovery.extraction.prompts import ExtractionPrompt
from domain.metamodel.entities import ENTITY_CLASSES
from domain.metamodel.entities.organization import Agent, Skill, Tool
from domain.metamodel.enums import EntityType
from foundry.errors import FoundryError
from foundry.synthesis.schema import KEY_FIELD_BY_ENTITY_TYPE

_IDENTITY_KEYS = frozenset({"name", "description"})


def parse_candidate_content(
    raw: Any,
    *,
    entity_type: EntityType,
    prompt: ExtractionPrompt,
    proposed_key: str,
) -> Skill | Tool | Agent:
    """Validate ``raw`` against ``prompt.response_schema``, then construct
    the real ``Skill``/``Tool``/``Agent`` with a platform-assigned identity
    (``proposed_key``) -- the LLM never controls it.

    ``Skill``/``Tool``/``Agent`` are plain ``MetamodelEntity`` catalog
    entities, not ``ProvenancedEntity`` -- they carry no provenance/
    confidence of their own, matching exactly how ``registry.py``'s
    ``_load_skills``/``_load_tools``/``_load_agents`` construct them from
    YAML with no provenance fields either. Provenance (``INFERRED``, tied
    to the originating pattern's confidence) lives one level up, on the
    ``CandidateSkill``/``CandidateTool``/``CandidateAgent`` wrapper that
    embeds this payload -- see ``foundry/run.py``.
    """
    try:
        jsonschema.validate(raw, prompt.response_schema)
    except jsonschema.ValidationError as exc:
        raise FoundryError(
            f"synthesized {entity_type.value} content failed schema validation: {exc.message}"
        ) from exc

    model = ENTITY_CLASSES[entity_type]
    key_field = KEY_FIELD_BY_ENTITY_TYPE[entity_type]
    content = {key: value for key, value in raw.items() if key not in _IDENTITY_KEYS}

    payload = {
        **content,
        "id": proposed_key,
        "name": raw["name"],
        "description": raw.get("description"),
        "entity_type": entity_type,
        key_field: proposed_key,
    }
    try:
        return model(**payload)
    except ValidationError as exc:
        raise FoundryError(
            f"synthesized {entity_type.value} content failed entity construction: {exc}"
        ) from exc
