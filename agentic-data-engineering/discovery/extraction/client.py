"""The `ExtractionClient` Protocol -- one interface, multiple real backends.

A live LLM-backed client and a golden-fixture-backed replay client for
hermetic tests are genuinely interchangeable implementations of one
operation: a prompt and a target schema go in, a dict comes out. That is
what earns this a `Protocol` (ADR-0007's "one interface, multiple real
backends" pattern) where a per-source-type parser would not have (see
ADR-0013) -- a dbt-lineage reading and a Markdown reading take different
inputs and are not interchangeable with each other, but *how one extraction
call is made* genuinely is.

Deliberately thin and provider-agnostic: `extract()` takes a prompt string
and a JSON Schema dict, returns a raw dict. Whatever a specific backend's
real call shape looks like (Anthropic's Messages API, GitHub Copilot CLI's
subprocess contract) is confined entirely to that backend's own adapter
module -- nothing above this Protocol needs to know or care.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ExtractionClient(Protocol):
    """Turns one prompt + schema into one structured response."""

    def extract(self, *, prompt: str, response_schema: dict[str, Any]) -> dict[str, Any]:
        """Return a dict intended to conform to `response_schema`.

        Conformance is not guaranteed by this call -- `parse_response.py` is
        the actual validation boundary, deliberately kept separate so every
        backend's output is checked identically regardless of how much (or
        how little) the backend itself enforces its own schema.
        """
        ...
