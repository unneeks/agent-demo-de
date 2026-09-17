"""Errors raised by the extraction subsystem."""

from __future__ import annotations


class ExtractionError(Exception):
    """An `ExtractionClient` could not produce a response at all.

    Distinct from a schema-conformance problem (`ExtractionSchemaError`):
    this is a transport/backend-level failure -- the process couldn't be
    invoked, the API call failed, the CLI binary wasn't found.
    """


class ExtractionSchemaError(Exception):
    """A response was obtained but does not conform to what was asked for.

    Raised by `parse_response.py`, never partially trusted -- the caller
    records this as a `DiscoveryFailure` and nothing is written to either
    persistence plane.
    """
