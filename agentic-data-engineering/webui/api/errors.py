"""Errors raised by the webui.api package.

Mirrors webui/errors.py's shape: name what a caller needs to act on,
rather than letting a raw `KeyError` or a silent fallback stand in for it.
"""

from __future__ import annotations


class ApiError(Exception):
    """Base class for every error this package raises."""


class UnknownAgentError(ApiError):
    """A request named an agent key not in `registry.agents`."""

    def __init__(self, agent_key: str) -> None:
        self.agent_key = agent_key
        super().__init__(f"no agent registered at key {agent_key!r}")


class ReplayBackendUnavailableError(ApiError):
    """The 'replay' llm_backend was requested, but `create_app()` was not
    given an `agent_fixtures_dir` -- a clean, documented failure, never a
    silent fallback to a different backend."""

    def __init__(self) -> None:
        super().__init__(
            "the 'replay' llm_backend is unavailable: this server was not configured with "
            "an agent_fixtures_dir (see create_app()'s agent_fixtures_dir parameter / "
            "scripts/run_web.py --agent-fixtures-dir)"
        )
