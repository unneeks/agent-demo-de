"""Errors raised by the agent_runtime package.

Each names what a caller needs to act on, rather than letting a raw
exception (a KeyError, a subprocess failure) surface unadorned. Mirrors
discovery/errors.py's and orchestrator/errors.py's shape.
"""

from __future__ import annotations


class AgentRuntimeError(Exception):
    """A structural precondition for running an agent failed."""


class UnknownToolActionError(AgentRuntimeError):
    """A tool call named a (tool_key, action_name) pair no backend can serve."""


class FixtureExhaustedError(AgentRuntimeError):
    """A ReplayAgentClient session ran out of recorded turns.

    Never repeats the last turn -- a fixture that has run out of script must
    fail loudly, not silently pretend the conversation is still scripted.
    """
