# API Gateway

`API Gateway` was the last layer `docs/architecture.md`'s layered diagram
still marked `(later)`. ADR-0018 explicitly left open "whether a future
API Gateway phase fronts the same backend `webui/` calls, or replaces
`webui/`'s in-process calls with HTTP ones" — this phase resolves that, on
explicit user direction: **same backend, same process, additive routes.**
`/api/*` lives in the same `FastAPI` app `webui/app.py` already builds,
alongside the six existing HTML routes, sharing one `ProjectGraphService`/
registry/repositories. See [ADR-0019](adr/0019-api-gateway.md) for the
full reasoning and the alternatives rejected.

## The one idea that must not be compromised

**Every write endpoint translates JSON-safe knobs into the same live
Python objects `orchestrator`/`agent_runtime` already require, server-side
only — never a client-supplied `ToolExecutor`/`AgentLLMClient`/
`ApprovalPolicy`, and never a client-supplied filesystem path for
OBSERVE.** Every route handler still calls one or two existing functions
and returns the real result — no new business logic, no new scoring, no
shadow response schema that could drift from the real dataclasses
(`webui/api/translate.py` is the one place this translation happens,
shared by every write route rather than duplicated four times).

## The eleven routes

Six read (`GET`), five write/action (`POST`):

```
GET  /api/projects                                              registered projects
GET  /api/projects/{id}                                          one project's dual-twin graph state
GET  /api/delivery-models                                          delivery model index
GET  /api/delivery-models/{model_key}                                phases, tasks, checklists, gates
GET  /api/marketplace                                                   catalog + IMPLEMENTED_BY staffing
GET  /api/evaluations[?subject=Type:id]                                   persisted Evaluations
GET  /api/projects/{id}/gates/{gate_key}[?model=][?evaluation_subject=]      live GateReadiness (always empty state)

POST /api/projects                        register a project
POST /api/entities                          ingest any entity, keyed by entity_type
POST /api/relationships                       ingest a relationship
POST /api/projects/{id}/evaluations             trigger a real evaluation run
POST /api/projects/{id}/gates/{key}/assess        trigger gate assessment with CALLER-SUPPLIED state
POST /api/projects/{id}/agent-runs                  trigger a real agent run
POST /api/projects/{id}/cycles                        trigger orchestrator.run_cycle()
```

`/api/projects` is a named convenience alias over the generic
`/api/entities` — a `Project` is a real `ENTITY_CLASSES` member and works
through either route. Both exist so the semantic distinction
`ProjectGraphService.register_project()` itself draws (a friendlier name
over `ingest_entity()`) stays visible at the API layer too.

## Worked example: the endpoint that finally closes the honesty gap

`GET /api/projects/{id}/gates/{key}` always supplies empty state for four
of `GateState`'s six dimensions (`present_artifact_kinds`,
`checklist_outcomes`, `satisfied_evidence`, `approvals`) — exactly like
its HTML counterpart, and exactly as honest about it (`docs/web-ui.md`).
`POST /api/projects/{id}/gates/{key}/assess` is the one place in this
entire codebase a caller can supply real values for those four dimensions
and get back a `GateReadiness` that actually reflects them:

```
GET  /api/projects/demo/gates/gate.architecture-review
  -> dimensions: ARTIFACTS satisfied=0/2 (always empty)

POST /api/projects/demo/gates/gate.architecture-review/assess
     {"present_artifact_kinds": ["solution-architecture"]}
  -> dimensions: ARTIFACTS satisfied=1/2 (the caller's real state)
```

`ChecklistOutcome` (a nested field of the same request body) is accepted
**uncritically** — matching `GateRequest`'s own existing shape exactly, not
recomputed or verified against `evaluate_checklist()`. A caller can submit
an internally-inconsistent or fabricated `ChecklistOutcome` and it will be
trusted as-is. Named here, not hidden.

## Translating JSON into live objects

`webui/api/translate.py` is the one place this happens, called by every
write route that needs it:

- `build_evaluation_request()` — `advance_agent_key: str | None` resolves
  to the real `registry.agents[...]` object (mutated in place by
  `advance_agent()` inside `run_evaluations()`), never a client-supplied
  `Agent` payload.
- `build_gate_request()` — a one-to-one field copy; `GateRequest` is
  already a plain dataclass with matching field names.
- `build_llm_client()`/`build_agent_run_request()` — `llm_backend` (one of
  `"replay"`/`"anthropic"`/`"copilot_cli"`) resolves to a real
  `AgentLLMClient`; `tool_executor` is **never** a request field —
  `SimulatedToolExecutor()` is hard-coded, matching every prior phase's
  "all tools simulated" discipline. `context_policy` is a **required**,
  fully caller-supplied `ContextPolicy` JSON body — there is no canonical
  default anywhere in the registry, and inventing one would silently
  constrain every caller ("never a literal," matching
  `EvaluationRequest.observed_values`'s own stated discipline).

## `POST .../cycles`: what it composes, and what it deliberately excludes

Reuses the exact same `translate.py` builders `evaluations.py`/`gates.py`/
`agent_runs.py` each call once — no duplicated translation logic — then
calls `orchestrator.cycle.run_cycle()` directly. `observe` is **always
`None`**: `ObserveRequest.repository_root` is a server-local filesystem
path, and with zero authentication in front of a read-write API, accepting
an arbitrary path from a remote caller is a real access-boundary risk, not
just a missing feature. `CycleReport.discovery` is always `None` through
this API — discovery stays `scripts/`-driven only.

**One documented subtlety.** A translation failure inside a list item
(e.g. an unknown `agent_key` in `agent_run_requests`) raises *before*
`run_cycle()` is entered, so it 4xxs the whole request rather than
appearing in `CycleReport.failed` — a malformed request is rejected
outright; a step that ran and failed is what `on_error="collect"` softly
records. A 422/404 on this endpoint is never a soft cycle failure.

## Response serialization

Every route returns the real object a matching `orchestrator`/
`agent_runtime`/`ProjectGraphService` function already returns —
`CycleReport`, `AgentRunOutcome`, `EvaluationOutcome`, `GateReadiness`,
`StoredEntity`, `Relationship` — with no hand-written shadow schema, even
though several of these (`CycleReport`, `AgentRunOutcome`,
`EvaluationOutcome`) are plain dataclasses nesting Pydantic models and
enums, not Pydantic themselves. Verified directly (not assumed): FastAPI's
dataclass response support serializes this whole family correctly with
zero extra code, confirmed by a live smoke test against the installed
FastAPI version before this was relied on anywhere.

## Errors

Every `/api/*` response, on failure, is a JSON envelope:
```json
{"error": "UnknownProjectError", "detail": "...", "status_code": 404}
```
The same exception types the HTML routes already raise (`UnknownProjectError`,
`UnknownGateError`, `UnknownDeliveryModelError`) render `error.html` on
`/projects/*` and the JSON envelope on `/api/*` — one handler per
exception type, branching on `request.url.path`'s `/api/` prefix
(`webui/app.py::_error_handler`), since FastAPI dispatches exception
handlers by type, not by path.

| Error | Status |
|---|---|
| `UnknownProjectError`, `UnknownGateError`, `UnknownDeliveryModelError` | 404 |
| `webui.api.errors.UnknownAgentError` | 404 |
| `KeyError` (defensive fallback — an unknown `suite_key`/similar reaching a raw registry lookup `translate.py` didn't already name) | 404 |
| `webui.api.errors.ReplayBackendUnavailableError` | 501 |
| `project_graph.errors.IngestionError` | 422 |
| `ValueError` (from `run_suite`/`analyze_change`/relationship validation/etc.) | 422 |
| `pydantic.ValidationError` (malformed request body) | 422 (FastAPI's own default) |
| `agent_runtime.errors.AgentRuntimeError` (+ `UnknownToolActionError`, `FixtureExhaustedError`) | 502 |

## What this is not

- **No authentication or authorization — stated more sharply than
  `docs/web-ui.md`'s read-only version.** Every write endpoint (arbitrary
  entity ingestion, agent runs that call live LLM backends, evaluation
  runs that mutate `Agent` lifecycle state) is reachable by anyone who can
  reach the process, with zero identity and zero audit trail of who
  triggered a write. This is not the same class of gap as a read-only
  dashboard having no login page.
- **No real tool execution, still.** `tool_executor` is never a request
  field; `SimulatedToolExecutor()` is always used.
- **OBSERVE/discovery is excluded from `POST .../cycles`.** No endpoint
  accepts a server-local filesystem path from a remote caller.
- **`ChecklistOutcome` is accepted uncritically** in the gate-assess
  endpoint — not recomputed or verified against `evaluate_checklist()`.
- **No run-history persistence.** `CycleReport`/`AgentRunOutcome` remain
  transient HTTP response bodies, never stored — the same gap
  `docs/web-ui.md` named for the dashboard, now also true of API
  responses.
- **No rate limiting, no request size limits** beyond FastAPI/Starlette/
  uvicorn framework defaults.
- **The `/api/projects` vs `/api/entities` overlap.** Both routes can
  register a project; there is no rule preventing a client from bypassing
  whichever one it didn't use. Harmless today (`register_project()` really
  is just `ingest_entity()`), but a seam a future phase should not assume
  away if the two are ever meant to diverge.
