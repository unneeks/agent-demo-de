"""`AnthropicExtractionClient` -- calls the real Anthropic Messages API.

Lazily imports `anthropic` so the hermetic unit suite never needs it
installed (`pip install -e ".[agent]"` pulls it in). Uses tool-use with a
single forced tool whose `input_schema` is the caller's `response_schema` --
the standard pattern for schema-constrained structured output against the
Messages API.

Implementation-time risk, stated plainly rather than glossed over (see
ADR-0013): the exact call shape here -- the tool-use/`tool_choice` contract,
the default model id, the SDK's exception hierarchy -- could not be verified
against live documentation from the environment this was written in (no
internet access). It must be checked against real `anthropic` SDK docs
before this is trusted in production; treat every constant below as a
best-effort placeholder, not a confirmed fact.
"""

from __future__ import annotations

import os
from typing import Any

from discovery.extraction.errors import ExtractionError

#: Unverified -- confirm the current recommended model id at implementation
#: time. Overridable via the constructor precisely because this is a guess.
DEFAULT_MODEL = "claude-sonnet-4-5"
_TOOL_NAME = "emit_extraction"


class AnthropicExtractionClient:
    """Live extraction backend, calling the Anthropic Messages API."""

    def __init__(self, *, api_key: str | None = None, model: str = DEFAULT_MODEL) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ExtractionError(
                "no Anthropic API key: set ANTHROPIC_API_KEY or pass api_key= explicitly"
            )
        self._model = model
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise ExtractionError(
                    "the 'anthropic' package is not installed -- pip install -e '.[agent]'"
                ) from exc
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def extract(self, *, prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        client = self._ensure_client()
        try:
            message = client.messages.create(
                model=self._model,
                max_tokens=4096,
                tools=[
                    {
                        "name": _TOOL_NAME,
                        "description": "Emit the extraction result conforming to the given schema.",
                        "input_schema": response_schema,
                    }
                ],
                tool_choice={"type": "tool", "name": _TOOL_NAME},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # the real SDK's exception hierarchy is unverified here
            raise ExtractionError(f"Anthropic Messages API call failed: {exc}") from exc

        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == _TOOL_NAME:
                return block.input  # type: ignore[no-any-return]

        raise ExtractionError(
            "Anthropic response contained no tool_use block for the forced extraction tool -- "
            "the call shape assumed here may not match the real API; verify against current docs"
        )
