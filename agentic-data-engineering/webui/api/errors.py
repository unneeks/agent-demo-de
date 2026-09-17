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


class UnknownWorkflowTemplateError(ApiError):
    """A request named a workflow template key not in the loaded catalog."""

    def __init__(self, template_key: str) -> None:
        self.template_key = template_key
        super().__init__(f"no workflow template registered at key {template_key!r}")


class UnknownWorkflowRunError(ApiError):
    """A request named a workflow run id this server has no record of --
    runs are in-process/in-memory only (docs/workflow-dashboard.md), so
    this is also what a caller sees after a server restart."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"no workflow run with id {run_id!r} (runs do not survive a server restart)")


class MissingWorkflowBackendError(ApiError):
    """A live workflow run was requested without naming a backend (either
    a top-level `live_backend` or a per-slot `live_agent_backends` entry)
    for one of the template's agent slots -- never silently defaulted,
    since a live run always needs a caller-named Harness/model."""

    def __init__(self, agent_slot_key: str) -> None:
        self.agent_slot_key = agent_slot_key
        super().__init__(
            f"live mode needs a backend for agent slot {agent_slot_key!r} -- set live_backend, "
            f"or live_agent_backends[{agent_slot_key!r}]"
        )
