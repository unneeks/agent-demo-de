"""Web UI + API Gateway -- one FastAPI app, two kinds of routes.

`webui/routes/` is a read-only, server-rendered dashboard over the
platform's persisted state (Phase 8) -- no browser-triggered write
anywhere in it, unchanged since it shipped. `webui/api/routes/` is a
read-write JSON API (Phase 9) -- register a project, ingest entities/
relationships, trigger evaluations/gate assessments/agent runs/cycles.
Both call ProjectGraphService/MetamodelRegistry/a persistence port/
orchestrator/agent_runtime functions directly, in-process, sharing one
`create_app()`-built app -- no second process, no HTTP hop between them.
See docs/web-ui.md and docs/api-gateway.md.
"""

from webui.app import create_app

__all__ = ["create_app"]
