"""`CopilotCliExtractionClient` -- shells out to the GitHub Copilot CLI.

A larger, differently-shaped risk than `AnthropicExtractionClient`, flagged
directly rather than glossed over (see ADR-0013): Copilot CLI is built as an
interactive suggestion/explanation tool, not a schema-constrained
structured-output API. There is no known guarantee it can be driven
non-interactively to return JSON conforming to an arbitrary
`response_schema` on the first try, or that any particular invocation flags
below exist on a given installed version. This adapter's job is to prompt
for JSON, extract the JSON object from whatever prose surrounds it in the
CLI's output, and hand the result to `parse_response.py` -- which already
rejects malformed/non-conforming output as a `DiscoveryFailure` rather than
partially trusting it, so a response that doesn't parse cleanly fails the
same safe way a wrong Anthropic field would.

Whether the CLI supports a non-interactive/scriptable mode at all, and what
its actual exit code and stdout/stderr contract look like, must be verified
against the real CLI at implementation time -- this could not be confirmed
from a planning/authoring environment with neither `copilot` nor `gh`
installed. No Python package extra is needed for this client: it depends on
an external binary on `PATH`, checked lazily at call time.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any

from discovery.extraction.errors import ExtractionError

#: Checked in this order; the first one found on PATH is used. Unverified
#: whether either supports the invocation shape assumed below.
_CANDIDATE_BINARIES = ("copilot", "gh")

_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)

_TIMEOUT_SECONDS = 120


def _find_binary() -> str:
    for name in _CANDIDATE_BINARIES:
        found = shutil.which(name)
        if found:
            return name
    raise ExtractionError(
        f"neither of {_CANDIDATE_BINARIES!r} was found on PATH -- install the GitHub Copilot CLI"
    )


def _build_command(binary: str, prompt: str) -> list[str]:
    """The invocation shape assumed for a non-interactive, single-turn call.

    Unverified against the real CLI. `gh copilot suggest -t shell "<prompt>"`
    and a hypothetical standalone `copilot -p "<prompt>"` are both plausible
    shapes depending on what is actually installed; this picks one per
    binary and documents the guess rather than silently assuming either is
    correct.
    """
    if binary == "copilot":
        return ["copilot", "-p", prompt]
    return ["gh", "copilot", "suggest", "-t", "shell", prompt]


def _extract_json_object(output: str) -> dict[str, Any]:
    match = _JSON_OBJECT_PATTERN.search(output)
    if match is None:
        raise ExtractionError(
            "no JSON object found in Copilot CLI output -- the CLI may not support "
            "structured/JSON output in this invocation mode"
        )
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Copilot CLI output contained text that looked like JSON but "
                               f"did not parse: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ExtractionError(
            f"Copilot CLI output parsed as JSON but was a {type(parsed).__name__}, not an object"
        )
    return parsed


class CopilotCliExtractionClient:
    """Live extraction backend, shelling out to the GitHub Copilot CLI."""

    def __init__(self, *, binary: str | None = None) -> None:
        self._binary = binary or _find_binary()

    def extract(self, *, prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        schema_text = json.dumps(response_schema, sort_keys=True)
        full_prompt = (
            f"{prompt}\n\nRespond with ONLY a single JSON object conforming to this JSON "
            f"Schema, no other text, no markdown code fence:\n{schema_text}"
        )
        command = _build_command(self._binary, full_prompt)
        try:
            completed = subprocess.run(  # noqa: S603 -- fixed argv, no shell
                command,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExtractionError(f"Copilot CLI invocation failed: {exc}") from exc

        if completed.returncode != 0:
            raise ExtractionError(
                f"Copilot CLI exited {completed.returncode}: {completed.stderr.strip()[:500]}"
            )
        return _extract_json_object(completed.stdout)
