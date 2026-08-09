"""Web UI -- a read-only, server-rendered dashboard over the platform's
persisted state. Every route calls ProjectGraphService/MetamodelRegistry/a
persistence port/orchestrator.gate.assess_gate_readiness() directly
in-process; there is no separate API layer and no browser-triggered write
anywhere in this package. See docs/web-ui.md.
"""

from webui.app import create_app

__all__ = ["create_app"]
