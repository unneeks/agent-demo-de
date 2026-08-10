"""Errors raised by the discovery package.

Each names what a caller needs to act on -- which file, which fixture, which
precondition -- rather than letting a raw exception surface unadorned.
"""

from __future__ import annotations


class DiscoveryError(Exception):
    """A structural precondition for discovery failed.

    Distinct from a ``DiscoverySkip`` (a soft per-file skip that lets the rest
    of a run continue): this is raised when discovery cannot proceed at all,
    e.g. a golden fixture is missing or stale, or a repository root doesn't
    exist.
    """
