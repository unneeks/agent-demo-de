# ADR-0018: A server-rendered, read-only Web UI, no API Gateway

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 8

## Context

`Web UI` and `API Gateway` were the only two layers `docs/architecture.md`'s
layered diagram still marked `(later)` after Phase 7. The user chose to
build only the Web UI, confirmed across two rounds of `AskUserQuestion`:

1. **Architecture**: server-rendered, in-process — no separate API layer.
2. **Interactivity**: read-only dashboard — no browser-triggered writes.
3. **Run-history scope**: a real gap surfaced and confirmed before the
   user chose — `CycleReport` (`orchestrator/cycle.py`) and
   `AgentRunReport` (`agent_runtime/loop.py`) are transient Python return
   values, never persisted anywhere in this codebase. The dashboard shows
   only what is genuinely persisted or queryable today; this phase does
   not touch `orchestrator/`or `agent_runtime/` to add persistence.

A second, more severe honesty finding, verified directly against
`engines/gates/readiness.py`'s `_score()` and
`ApprovalGate._gate_must_require_something`: a real gate is only
guaranteed to require something in **at least one** of six fields, not all
six. Because a live gate-readiness view always supplies empty state for
the four dimensions with no real assembler
(`present_artifact_kinds`/`checklist_outcomes`/`satisfied_evidence`/
`approvals`), a gate that happens to require nothing in one of those four
scores a **false 100%** (`_score()`'s own "requires nothing is trivially
complete" rule), while a gate that requires something there scores a
**misleading 0%**. Neither reading is real gate health for those four
dimensions.

## Decision

**A new top-level package, `webui/`**, with `create_app(registry, metadata,
graph) -> FastAPI` as its entry point — the same three-constructor-argument
dependency-injection discipline every other module in this codebase already
uses (`ProjectGraphService(metadata, graph)`, `run_cycle(service, registry,
...)`). Six `GET` routes, each a thin function calling one or two existing
methods and rendering the real returned object with Jinja2. No new business
logic, no new scoring, no new persistence writes.

**Judgment call: server-rendered-in-process over a separate API+JS
frontend.** Rejected building a JSON API layer and a decoupled JS frontend:
the user explicitly scoped this to one new layer, not two, and every other
module in this codebase already follows "call the port/service directly,
no network hop" (ADR-0007's precedent). Cost, stated honestly: this UI can
never be consumed by anything except a browser rendering the HTML this
process produces — nothing programmatic, inside or outside this codebase,
has anything to call. **API Gateway is now the only layer still marked
`(later)`.**

**Judgment call: persisted-state-only scope, no run-history view.**
Rejected persisting `CycleReport`/`AgentRunReport` (or building any storage
for them) as out of scope for a UI phase — that decision belongs to a
future, dedicated persistence phase, not bundled into rendering. The
dashboard's six routes read only what is already durable:
`MetadataRepository`/`GraphRepository` state, the loaded
`MetamodelRegistry`/`LoadedDeliveryModel`, and live computation via the
existing, unmodified `orchestrator.gate.assess_gate_readiness()`.

**Judgment call: the gate-readiness honesty banner is unconditional, not
per-score.** A 100% and a 0% are *both* potentially misleading for the four
unassessable dimensions, for opposite reasons — a caveat only on low scores
would let a false-100% pass as real. The template names all four
dimensions explicitly and states plainly that neither reading reflects
verified gate health, while EVALUATIONS/TRACEABILITY (which do have real
assemblers — Phase 5's `passed_evaluation_keys()`, Phase 6's
`service.assess_traceability()`) render as ordinary scores with no caveat.

**Package name: `webui/`**, not `web`/`webapp`. Neither collides with
anything in the repo today, but `webui/` reads unambiguously as "renders
HTML for humans" and keeps `docs/web-ui.md`/the package name/the
architecture diagram's "Web UI" label textually aligned end to end.

**One dependency-extra addition:** `web = ["fastapi>=0.110", "uvicorn>=0.27",
"jinja2>=3.1", "httpx>=0.27"]`. Unlike `agent`'s `anthropic` dependency
(import-deferred inside method bodies, so `pip install -e ".[dev]"` alone
still runs the full `tests/unit` suite), `fastapi` cannot be deferred the
same way — `webui/app.py` and every route module need it at module import
time. Every `tests/unit/test_webui_*.py` file therefore opens with
`pytest.importorskip("fastapi")`/`pytest.importorskip("httpx")`, so a plain
`.[dev]` install **skips** these files visibly rather than failing
collection — verified directly: `pytest tests/unit -q` with `fastapi`/
`httpx`/`starlette` uninstalled reports 576 passed, 6 skipped, no failures.

## Consequences

**Good.** Every one of `ProjectGraphService`'s ten public methods and
`MetamodelRegistry`'s full catalog now has a real, human-visible viewer.
The `/projects/{id}` route reuses `snapshot()`'s exact traversal shape,
proving that pattern is genuinely reusable outside its original
snapshotting purpose. The gate-readiness honesty finding is a real,
previously-undocumented sharp edge in `GateState`'s caller-supplied fields
that this phase surfaces rather than papering over.

**Costs, stated honestly.** No authentication or authorization exists —
every route is open; this is a local/demo-only view, not a deployable
multi-tenant dashboard. No pagination — fine at the worked model's current
size, a real scaling limit at any larger one. No real-time updates. An
entity ingested without an explicit connecting relationship from its
project (a plain `project_ref` field is not a graph edge) is invisible to
both this view and `snapshot()` alike — pre-existing `ProjectGraphService`
behavior this phase did not introduce but did surface by building the
first thing that renders it for a human to notice.

## Alternatives rejected

**A separate JSON API layer plus a JS frontend** (the "Both together"
option the user did not choose). Rejected per the user's explicit
one-layer-not-two scope.

**Persisting `CycleReport`/`AgentRunReport`** to give the dashboard a
run-history page. Rejected as out-of-scope UI-phase creep into
already-shipped, tested, documented modules (`orchestrator/`,
`agent_runtime/`) — a future phase's decision, not this one's.

**A per-dimension caveat only on low scores** for the gate-readiness view.
Rejected — a false 100% is equally misleading and would pass silently
under that design; the banner is unconditional for all four unassessable
dimensions regardless of what they happen to score.

**Deferring `fastapi` imports inside method bodies**, mirroring
`agent_runtime/anthropic_client.py`'s pattern, to avoid the
`pytest.importorskip` guard. Rejected as impractical: a whole web
framework's routing/templating machinery needs to be wired at module
import time, unlike a single API client class that only needs its SDK
inside one method.
