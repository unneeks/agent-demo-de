"""Errors raised by the Foundry orchestration package."""

from __future__ import annotations


class FoundryError(Exception):
    """A structural precondition for a Foundry run failed, or a synthesis
    call/response could not be trusted -- schema-violating LLM output, a
    missing/stale replay fixture, a transport-level client failure.
    """
