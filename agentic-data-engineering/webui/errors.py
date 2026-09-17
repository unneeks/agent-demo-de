"""Errors raised by the webui package.

Mirrors project_graph/errors.py's shape: name what a caller needs to act
on. Routes raise the real domain errors where they already exist
(project_graph.errors.UnknownProjectError, orchestrator.errors.
UnknownGateError) rather than reinventing 404 logic -- this module only
adds the one error no existing module has.
"""

from __future__ import annotations


class WebUIError(Exception):
    """Base class for every error this package raises."""


class UnknownDeliveryModelError(WebUIError):
    """A route named a delivery model key the registry doesn't have."""

    def __init__(self, model_key: str) -> None:
        self.model_key = model_key
        super().__init__(f"no delivery model registered at key {model_key!r}")
