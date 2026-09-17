"""`ReplayExtractionClient` -- golden-fixture-backed, hermetic.

Covers correct lookup by path, the request-hash staleness check, and a
missing-fixture failure -- the three ways replay must fail loudly rather
than silently substitute a wrong or stale answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from discovery.errors import DiscoveryError
from discovery.extraction.prompts import build_technical_prompt
from discovery.extraction.replay_client import (
    GoldenFixture,
    ReplayExtractionClient,
    build_request_hash,
    slug_for_path,
    source_path_from_prompt,
)


@pytest.fixture
def prompt():
    return build_technical_prompt(relative_path=Path("models/p1.sql"), content="select 1", source_kind="sql")


def _write_fixture(fixtures_dir: Path, *, source_path: str, request_hash: str, raw_response: dict) -> None:
    fixture = GoldenFixture(
        source_path=source_path,
        request_hash=request_hash,
        raw_response=raw_response,
        backend="anthropic",
        recorded_at="2026-01-01T00:00:00Z",
    )
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    (fixtures_dir / f"{slug_for_path(source_path)}.json").write_text(json.dumps(fixture.to_json()))


class TestSlugForPath:
    def test_slashes_become_double_underscores(self) -> None:
        assert slug_for_path("models/staging/a.sql") == "models__staging__a.sql"


class TestSourcePathFromPrompt:
    def test_extracts_the_file_line(self, prompt) -> None:
        assert source_path_from_prompt(prompt.prompt) == "models/p1.sql"

    def test_a_prompt_without_a_file_line_raises(self) -> None:
        with pytest.raises(DiscoveryError, match="File:"):
            source_path_from_prompt("no file line here")


class TestReplayExtractionClient:
    def test_loads_the_matching_fixture(self, tmp_path: Path, prompt) -> None:
        raw = {"entities": [], "relationships": []}
        request_hash = build_request_hash(prompt.prompt, prompt.response_schema)
        _write_fixture(tmp_path, source_path="models/p1.sql", request_hash=request_hash, raw_response=raw)

        client = ReplayExtractionClient(tmp_path)
        result = client.extract(prompt=prompt.prompt, response_schema=prompt.response_schema)
        assert result == raw

    def test_missing_fixture_raises_clearly(self, tmp_path: Path, prompt) -> None:
        client = ReplayExtractionClient(tmp_path)
        with pytest.raises(DiscoveryError, match="no golden fixture"):
            client.extract(prompt=prompt.prompt, response_schema=prompt.response_schema)

    def test_stale_fixture_content_hash_mismatch_raises(self, tmp_path: Path, prompt) -> None:
        _write_fixture(
            tmp_path,
            source_path="models/p1.sql",
            request_hash="not-the-real-hash",
            raw_response={"entities": [], "relationships": []},
        )
        client = ReplayExtractionClient(tmp_path)
        with pytest.raises(DiscoveryError, match="stale"):
            client.extract(prompt=prompt.prompt, response_schema=prompt.response_schema)

    def test_a_schema_change_also_counts_as_stale(self, tmp_path: Path) -> None:
        """The staleness key covers (prompt, schema) together -- a prompts.py
        edit that changes the schema for the same file content must also
        invalidate the recording, not just a source-file edit."""
        prompt_a = build_technical_prompt(relative_path=Path("f.sql"), content="select 1", source_kind="sql")
        request_hash = build_request_hash(prompt_a.prompt, prompt_a.response_schema)
        _write_fixture(
            tmp_path, source_path="f.sql", request_hash=request_hash, raw_response={"entities": [], "relationships": []}
        )
        client = ReplayExtractionClient(tmp_path)

        different_schema = dict(prompt_a.response_schema, title="a different schema")
        with pytest.raises(DiscoveryError, match="stale"):
            client.extract(prompt=prompt_a.prompt, response_schema=different_schema)


class TestGoldenFixtureRoundTrip:
    def test_to_json_from_json_round_trips(self) -> None:
        fixture = GoldenFixture(
            source_path="a.sql",
            request_hash="abc",
            raw_response={"entities": [], "relationships": []},
            backend="anthropic",
            recorded_at="2026-01-01T00:00:00Z",
        )
        assert GoldenFixture.from_json(fixture.to_json()) == fixture
