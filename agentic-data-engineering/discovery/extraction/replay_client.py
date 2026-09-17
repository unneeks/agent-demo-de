"""`ReplayExtractionClient` -- golden-fixture-backed, hermetic, fast.

Design note, a deliberate refinement of what was originally planned as a
raw-file-content-hash check: `ExtractionClient.extract()` only ever receives
`(prompt, response_schema)`, not a file path or raw file bytes -- so
staleness is keyed on a hash of exactly that pair (the "request hash"),
not on separately re-reading and re-hashing the source file. This is
strictly more inclusive than a content-only hash: it also catches a
`discovery.extraction.prompts` change (a schema or prompt-wording edit)
invalidating a recording, not just a source file edit, and it needs no
side-channel file access the Protocol doesn't already provide. The file
being extracted is identified for fixture lookup by parsing the `File: ...`
line every prompt built by `discovery.extraction.prompts` starts with --
parsing the prompt is honest here, not fragile, because this client and
that module are maintained together and the convention is asserted by
`build_request_hash`'s own round-trip tests.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from discovery.errors import DiscoveryError
from discovery.hashing import sha256_text

_FILE_LINE_PATTERN = re.compile(r"^File: (.+)$", re.MULTILINE)


def slug_for_path(source_path: str) -> str:
    """Human-navigable, diff-reviewable fixture filename stem for one source path."""
    return source_path.replace("/", "__")


def build_request_hash(prompt: str, response_schema: dict[str, Any]) -> str:
    """The staleness key: a hash of exactly what one `extract()` call receives."""
    canonical_schema = json.dumps(response_schema, sort_keys=True, separators=(",", ":"))
    return sha256_text(prompt + "\x00" + canonical_schema)


def source_path_from_prompt(prompt: str) -> str:
    match = _FILE_LINE_PATTERN.search(prompt)
    if match is None:
        raise DiscoveryError(
            "prompt has no 'File: <path>' line -- ReplayExtractionClient can only serve "
            "prompts built by discovery.extraction.prompts"
        )
    return match.group(1)


@dataclass(frozen=True)
class GoldenFixture:
    source_path: str
    request_hash: str
    raw_response: dict[str, Any]
    backend: str
    recorded_at: str

    def to_json(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "request_hash": self.request_hash,
            "raw_response": self.raw_response,
            "backend": self.backend,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> GoldenFixture:
        return cls(
            source_path=data["source_path"],
            request_hash=data["request_hash"],
            raw_response=data["raw_response"],
            backend=data["backend"],
            recorded_at=data["recorded_at"],
        )


class ReplayExtractionClient:
    """Serves committed golden fixtures instead of making a live call.

    Hermetic and fast: no network, no credentials, no external binary. Used
    by every hermetic discovery test, including the worked-example
    assertions against the real sibling project's recorded fixtures.
    """

    def __init__(self, fixtures_dir: Path) -> None:
        self._fixtures_dir = fixtures_dir

    def extract(self, *, prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        source_path = source_path_from_prompt(prompt)
        fixture_path = self._fixtures_dir / f"{slug_for_path(source_path)}.json"
        if not fixture_path.exists():
            raise DiscoveryError(
                f"no golden fixture for {source_path!r} at {fixture_path} -- run "
                "scripts/record_extraction_fixtures.py"
            )
        fixture = GoldenFixture.from_json(json.loads(fixture_path.read_text(encoding="utf-8")))
        expected_hash = build_request_hash(prompt, response_schema)
        if fixture.request_hash != expected_hash:
            raise DiscoveryError(
                f"golden fixture for {source_path!r} is stale -- its prompt or schema no "
                "longer matches what was recorded (source content or extraction schema "
                "changed since recording). Rerun scripts/record_extraction_fixtures.py."
            )
        return fixture.raw_response
