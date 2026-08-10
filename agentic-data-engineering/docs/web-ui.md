# Web UI

`Web UI` and `API Gateway` were the only two layers `docs/architecture.md`'s
layered diagram still marked `(later)` after Phase 7. This phase builds
**only** the Web UI, on explicit user direction: a server-rendered Python
dashboard whose route handlers call `ProjectGraphService`/
`MetamodelRegistry`/the query facade **directly in-process** — no separate
JSON API layer, no separate JS frontend, no network hop between "UI" and
"backend." One new layer, not two. See
[ADR-0018](adr/0018-web-ui.md) for the full reasoning and the alternatives
rejected.

## The one idea that must not be compromised

**`webui/` is a rendering layer, not a new architectural layer.** Every
route handler is a thin function: resolve dependencies from
`request.app.state` → call one or two existing methods on
`ProjectGraphService`/`MetamodelRegistry`/a persistence port/
`orchestrator.gate.assess_gate_readiness()` → pass the real returned object
straight into a Jinja2 template. No new business logic, no new scoring, no
new persistence writes anywhere in this package.

## The six routes

```
GET /                                              registered projects
GET /projects/{project_id}                          one project's dual-twin graph state
GET /delivery-models                                  delivery model index
GET /delivery-models/{model_key}                       phases, tasks, checklists, gates
GET /marketplace                                          catalog + IMPLEMENTED_BY staffing
GET /evaluations[?subject=Type:id]                          persisted Evaluations
GET /projects/{id}/gates/{gate_key}[?model=][?evaluation_subject=]  live GateReadiness
```

Every route is `GET`. There is no register-project route, no cycle/agent-run
trigger, no gate-approval action — a read-only dashboard, exactly as scoped.

## Worked example: `/projects/{id}` reuses `snapshot()`'s traversal, read-only

`ProjectGraphService.snapshot()` discovers a project's transitive graph
closure to *pin* it into a `ProjectSnapshot`. `webui/routes/project_graph.py`
reuses the identical traversal and relationship-filter shape to *render* it
instead — no `ProjectSnapshot` is built or ingested, nothing is written:

```python
project_ref = EntityRef(type=EntityType.PROJECT, id=project_id).identity
discovered = {str(project_ref): project_ref}
for result in graph.traverse(project_ref, max_depth=25, direction="both"):
    discovered.setdefault(str(result.ref), result.ref)
```

A ref reached by traversal with no metadata row (a catalog/registry node —
an `EngineeringRole`, a `Capability` definition) is counted and shown
plainly as "N graph nodes reached that are catalog references, not
project-owned data" — the same distinction `snapshot()`'s own docstring
draws, made visible in the template instead of only in a comment.

**A real gap this surfaced, worth naming:** an entity's `project_ref` field
(e.g. `Pipeline.project_ref`) is a plain data reference, not a traversable
graph edge — an entity is only reachable from a project's graph node via an
explicit relationship (`CONTAINS`, in every existing worked example and
test fixture). A caller that ingests project-scoped entities without also
writing the connecting edge will find them invisible to this view and to
`snapshot()` alike; this is pre-existing `ProjectGraphService` behavior,
not something this phase introduces or changes.

## Worked example: the gate-readiness honesty banner

`GET /projects/demo/gates/gate.architecture-review` calls
`orchestrator.gate.assess_gate_readiness()` unmodified, with a `GateRequest`
whose four caller-supplied-only fields (`present_artifact_kinds`,
`checklist_outcomes`, `satisfied_evidence`, `approvals`) are left at their
empty defaults. Verified directly against `engines/gates/readiness.py`'s
`_score()` (*"a dimension requiring nothing is trivially complete"*) and
`ApprovalGate._gate_must_require_something` (a real gate is only guaranteed
to require something in **at least one** of six fields, not all six): a
resulting 100% for ARTIFACTS/CHECKLISTS/EVIDENCE/APPROVALS means the gate
happens to require nothing there, not that it was verified; any other score
for those four means zero real detection capability, not an actual
finding. The rendered page carries a fixed, unconditional banner saying so
— not a per-score caveat — while EVALUATIONS (`passed_evaluation_keys()`)
and TRACEABILITY (`service.assess_traceability()`) render as ordinary live
scores, sourced from real persisted state.

## Running it

```bash
pip install -e ".[web]"
python scripts/run_web.py                    # in-memory backend, starts empty
python scripts/run_web.py --seed-demo-project # hand-builds one small project to look at
python scripts/run_web.py --backend postgres-neo4j --postgres-dsn ... --neo4j-uri ...
```

There is no register-project route in this read-only phase — data has to
already exist via discovery, the orchestrator, or an agent run against the
same repositories the script is pointed at (or the `--seed-demo-project`
shortcut, which duplicates a tiny amount of `tests/conftest.py`-style
entity construction locally, since scripts must not import from the test
tree).

## Errors

| Error | Rendered as |
|---|---|
| `project_graph.errors.UnknownProjectError` | 404 (`error.html`) |
| `orchestrator.errors.UnknownGateError` | 404 (`error.html`) |
| `webui.errors.UnknownDeliveryModelError` | 404 (`error.html`) |
| `EntityRef.parse()` on a malformed `?subject=`/`?evaluation_subject=` | inline 4xx on the requesting page, never a 500 |

## What this is not

- **No writes from the browser.** Every route is `GET`; no register-project,
  no cycle/agent-run trigger, no gate-approval action anywhere in `webui/`.
- **No API Gateway, no JSON API.** No `/api/*` route, no machine-consumable
  endpoint — reachable only by a browser rendering the HTML this process
  returns. API Gateway remains the one layer still `(later)`.
- **No cycle/agent-run history.** `CycleReport` (`orchestrator/cycle.py`)
  and `AgentRunReport` (`agent_runtime/loop.py`) are transient Python
  return values, never persisted anywhere in this codebase — this phase
  does not touch `orchestrator/`or `agent_runtime/` to add persistence for
  them, and there is deliberately no "Cycle Runs"/"Agent Runs" page.
- **No authentication or authorization.** Every route is open — a local/
  demo-only read-only view, not a deployable multi-tenant dashboard.
- **No real-time updates.** No websocket/polling/SSE; each page load is one
  fresh set of reads.
- **No pagination.** `metadata.list(...)`/`graph.traverse(...)` render in
  full — fine at the worked model's current size, named as a real scaling
  limit, not silently worked around.
- **The four missing `GateState` assemblers stay missing.** This phase
  surfaces that gap honestly in the UI (the unconditional banner) rather
  than papering over it with invented data.
