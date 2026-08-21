"""``ReplaySynthesisClient`` -- golden-fixture-backed, hermetic, fast.

Implements the same ``ExtractionClient`` Protocol
(``discovery.extraction.client.ExtractionClient``) structurally -- no
inheritance needed, the Protocol is ``@runtime_checkable`` and duck-typed
-- so it is interchangeable with ``AnthropicExtractionClient``/
``CopilotCliExtractionClient`` wherever ``foundry/run.py`` expects a
client.

Unlike ``discovery.extraction.replay_client.ReplayExtractionClient``,
which parses a ``File: ...`` line out of discovery's file-extraction
prompt convention to locate a fixture, Foundry's fixtures are
**content-addressed**: the request hash itself (reusing
``build_request_hash`` directly -- it is already fully generic over
``(prompt, response_schema)``, not file-specific) is the fixture
filename, since a Foundry prompt describes a pattern, not a file, and has
no equivalent "path" to key on. Strictly simpler than discovery's own
scheme, not a re-implementation of its file-lookup logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discovery.extraction.replay_client import build_request_hash
from foundry.errors import FoundryError


@dataclass(frozen=True)
class SynthesisFixture:
    #: Human-readable label only (e.g. "skill:pattern.pipeline_shape...") --
    #: not used for lookup, purely so a committed fixture file is legible
    #: in review; lookup is keyed on request_hash alone.
    label: str
    request_hash: str
    raw_response: dict[str, Any]
    backend: str
    recorded_at: str

    def to_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "request_hash": self.request_hash,
            "raw_response": self.raw_response,
            "backend": self.backend,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SynthesisFixture:
        return cls(
            label=data["label"],
            request_hash=data["request_hash"],
            raw_response=data["raw_response"],
            backend=data["backend"],
            recorded_at=data["recorded_at"],
        )


class ReplaySynthesisClient:
    """Serves committed golden fixtures instead of making a live LLM call."""

    def __init__(self, fixtures_dir: Path) -> None:
        self._fixtures_dir = fixtures_dir

    def extract(self, *, prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        request_hash = build_request_hash(prompt, response_schema)
        fixture_path = self._fixtures_dir / f"{request_hash}.json"
        if not fixture_path.exists():
            raise FoundryError(
                f"no golden synthesis fixture for request hash {request_hash!r} at "
                f"{fixture_path} -- hand-author one under tests/fixtures/foundry/"
            )
        fixture = SynthesisFixture.from_json(json.loads(fixture_path.read_text(encoding="utf-8")))
        if fixture.request_hash != request_hash:
            raise FoundryError(
                f"golden synthesis fixture at {fixture_path} is stale -- its prompt or schema "
                "no longer matches what was recorded"
            )
        return fixture.raw_response
