"""``foundry/synthesis/``: the one LLM step in Marketplace Foundry.

Hermetic -- every test here uses ``ReplaySynthesisClient`` against
``tmp_path``-built fixtures, never a live call, mirroring
``test_discovery_replay_client.py``'s own mechanism-testing style (the
committed golden fixtures under ``tests/fixtures/foundry/`` are exercised
end-to-end by ``test_foundry_run.py`` instead).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest

from domain.metamodel.enums import EntityType
from foundry.errors import FoundryError
from foundry.synthesis.parse_response import parse_candidate_content
from foundry.synthesis.prompts import build_candidate_prompt
from foundry.synthesis.replay_client import ReplaySynthesisClient, SynthesisFixture
from foundry.synthesis.schema import candidate_content_schema_for
from discovery.extraction.replay_client import build_request_hash

from tests.conftest import make_pattern

PATTERN = make_pattern(
    "pattern.pipeline_shape.dbt_model.airflow",
    common_activity="dbt_model",
    common_technology="airflow",
    common_inputs=["raw_orders"],
    common_outputs=["stg_orders"],
    similarity_score=1.0,
    confidence=1.0,
)

SKILL_RESPONSE = {
    "name": "Staging Orders Transform",
    "description": "Transforms raw order data into staged orders via a dbt model on Airflow.",
    "inputs": {"raw_orders": "raw order records"},
    "outputs": {"stg_orders": "staged order records"},
    "required_tools": ["dbt"],
    "risk_level": "LOW",
    "deterministic": True,
}


def _write_fixture(fixtures_dir: Path, *, prompt: str, response_schema: dict, raw_response: dict) -> str:
    request_hash = build_request_hash(prompt, response_schema)
    fixture = SynthesisFixture(
        label="test",
        request_hash=request_hash,
        raw_response=raw_response,
        backend="replay",
        recorded_at=datetime.now(timezone.utc).isoformat(),
    )
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / f"{request_hash}.json").write_text(json.dumps(fixture.to_json()))
    return request_hash


class TestCandidateContentSchema:
    def test_skill_schema_adds_name_and_description_and_drops_skill_key(self) -> None:
        schema = candidate_content_schema_for(EntityType.SKILL)
        assert "name" in schema["properties"]
        assert "description" in schema["properties"]
        assert "skill_key" not in schema["properties"]
        assert "confidence" not in schema["properties"]
        assert set(schema["required"]) == {"name", "description"}

    def test_tool_schema_drops_tool_key(self) -> None:
        schema = candidate_content_schema_for(EntityType.TOOL)
        assert "tool_key" not in schema["properties"]
        assert "name" in schema["properties"]

    def test_agent_schema_drops_agent_key_and_lifecycle_fields(self) -> None:
        schema = candidate_content_schema_for(EntityType.AGENT)
        assert "agent_key" not in schema["properties"]
        assert "status" not in schema["properties"]
        assert "certification_status" not in schema["properties"]
        # role_key is a plain string field, not identity or lifecycle -- the
        # LLM still proposes it (a known, named Phase-10 limitation: it is
        # not validated against the real EngineeringRole catalog).
        assert "role_key" in schema["properties"]

    def test_unknown_entity_type_raises(self) -> None:
        with pytest.raises(ValueError, match="no candidate content schema"):
            candidate_content_schema_for(EntityType.PROJECT)


class TestBuildCandidatePrompt:
    def test_prompt_mentions_pattern_facts(self) -> None:
        prompt = build_candidate_prompt(PATTERN, [], EntityType.SKILL)
        assert "dbt_model" in prompt.prompt
        assert "airflow" in prompt.prompt
        assert "raw_orders" in prompt.prompt
        assert prompt.response_schema == candidate_content_schema_for(EntityType.SKILL)

    def test_different_entity_types_produce_different_schemas(self) -> None:
        skill_prompt = build_candidate_prompt(PATTERN, [], EntityType.SKILL)
        tool_prompt = build_candidate_prompt(PATTERN, [], EntityType.TOOL)
        assert skill_prompt.response_schema != tool_prompt.response_schema


class TestParseCandidateContent:
    def test_a_conforming_response_constructs_the_real_entity(self) -> None:
        prompt = build_candidate_prompt(PATTERN, [], EntityType.SKILL)
        skill = parse_candidate_content(
            SKILL_RESPONSE, entity_type=EntityType.SKILL, prompt=prompt, proposed_key="skill.p1"
        )
        assert skill.skill_key == "skill.p1"
        assert skill.name == "Staging Orders Transform"
        assert skill.inputs == {"raw_orders": "raw order records"}
        assert skill.risk_level == "LOW"

    def test_a_non_conforming_response_is_rejected_wholesale(self) -> None:
        prompt = build_candidate_prompt(PATTERN, [], EntityType.SKILL)
        bad_response = {"name": "X"}  # missing required "description"
        with pytest.raises(FoundryError, match="failed schema validation"):
            parse_candidate_content(
                bad_response, entity_type=EntityType.SKILL, prompt=prompt, proposed_key="skill.p1"
            )

    def test_schema_conforming_but_semantically_invalid_content_fails_entity_construction(self) -> None:
        prompt = build_candidate_prompt(PATTERN, [], EntityType.AGENT)
        # execution_model=EXTERNAL_AGENT with no external_provider is legal
        # JSON Schema (both are plain strings/enums) but illegal per Agent's
        # own model validator -- the second defense layer.
        response = {
            "name": "X",
            "description": "Y",
            "role_key": "data-model-engineer",
            "execution_model": "EXTERNAL_AGENT",
        }
        jsonschema.validate(response, prompt.response_schema)  # sanity: schema-conformant
        with pytest.raises(FoundryError, match="failed entity construction"):
            parse_candidate_content(
                response, entity_type=EntityType.AGENT, prompt=prompt, proposed_key="agent.p1"
            )


class TestReplaySynthesisClient:
    def test_serves_a_matching_fixture(self, tmp_path: Path) -> None:
        prompt = build_candidate_prompt(PATTERN, [], EntityType.SKILL)
        _write_fixture(
            tmp_path, prompt=prompt.prompt, response_schema=prompt.response_schema, raw_response=SKILL_RESPONSE
        )
        client = ReplaySynthesisClient(tmp_path)
        raw = client.extract(prompt=prompt.prompt, response_schema=prompt.response_schema)
        assert raw == SKILL_RESPONSE

    def test_missing_fixture_raises_clearly(self, tmp_path: Path) -> None:
        prompt = build_candidate_prompt(PATTERN, [], EntityType.SKILL)
        client = ReplaySynthesisClient(tmp_path)
        with pytest.raises(FoundryError, match="no golden synthesis fixture"):
            client.extract(prompt=prompt.prompt, response_schema=prompt.response_schema)

    def test_a_schema_change_makes_a_recorded_fixture_stale(self, tmp_path: Path) -> None:
        prompt = build_candidate_prompt(PATTERN, [], EntityType.SKILL)
        request_hash = build_request_hash(prompt.prompt, prompt.response_schema)
        # Write a fixture under the OLD (correct) hash, but with its stored
        # request_hash field corrupted to simulate a stale recording.
        fixture = SynthesisFixture(
            label="test", request_hash="not-the-real-hash", raw_response=SKILL_RESPONSE,
            backend="replay", recorded_at=datetime.now(timezone.utc).isoformat(),
        )
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / f"{request_hash}.json").write_text(json.dumps(fixture.to_json()))
        client = ReplaySynthesisClient(tmp_path)
        with pytest.raises(FoundryError, match="is stale"):
            client.extract(prompt=prompt.prompt, response_schema=prompt.response_schema)

    def test_end_to_end_round_trip_produces_a_real_candidate_payload(self, tmp_path: Path) -> None:
        prompt = build_candidate_prompt(PATTERN, [], EntityType.SKILL)
        _write_fixture(
            tmp_path, prompt=prompt.prompt, response_schema=prompt.response_schema, raw_response=SKILL_RESPONSE
        )
        client = ReplaySynthesisClient(tmp_path)
        raw = client.extract(prompt=prompt.prompt, response_schema=prompt.response_schema)
        skill = parse_candidate_content(
            raw, entity_type=EntityType.SKILL, prompt=prompt, proposed_key="skill.p1"
        )
        assert skill.skill_key == "skill.p1"
        assert skill.name == SKILL_RESPONSE["name"]
