"""Errors raised by the orchestrator package.

Each names what a caller needs to act on, rather than letting a raw
exception (a KeyError, an AttributeError) surface unadorned.
"""

from __future__ import annotations


class OrchestratorError(Exception):
    """A structural precondition for running a cycle failed.

    Distinct from a ``CycleFailure`` (a soft per-step failure recorded and
    collected so the rest of a cycle can continue): this is raised when the
    cycle cannot proceed at all, e.g. an ``ObserveRequest``'s project doesn't
    match the cycle's own ``project_ref``.
    """


class UnknownGateError(OrchestratorError):
    """A ``GateRequest`` names a gate key the delivery model doesn't have."""
