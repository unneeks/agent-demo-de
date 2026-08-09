# ADR-0019: A read-write API Gateway, same process as the Web UI

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 9

## Context

`API Gateway` was the last layer `docs/architecture.md`'s layered diagram
still marked `(later)`. ADR-0018 explicitly deferred the question:

> "A future API Gateway phase would need to decide whether it fronts the
> same backend `webui/` calls, or replaces `webui/`'s in-process calls
> with HTTP ones."

Two confirmed `AskUserQuestion` answers resolve this:

1. **Read-write, not read-only** — the API exposes both reads (mirroring
   `webui/`'s six views as JSON) and action endpoints: register a project,
   ingest raw entities/relationships, trigger an evaluation run, trigger a
   gate assessment with caller-supplied `GateState` inputs, trigger an
   agent run, trigger a full `run_cycle()`.
2. **One process, two routers** — `/api/*` lives in the same `FastAPI` app
   `webui/app.py` already builds, sharing one `ProjectGraphService`/
   registry/repositories with the six existing HTML routes, which stay
   unmodified in behavior (every `test_webui_*.py` assertion keeps passing
   byte-for-byte, verified by a new regression test file,
   `test_webui_html_unchanged.py`).

**The central technical challenge, verified directly against real source
before designing anything:** every orchestrator/agent_runtime entry point
that "does something" takes live Python objects as arguments —
`AgentRunRequest.llm_client`/`.tool_executor`/`.approval_policy`,
`EvaluationRequest.advance_agent` (must be the real `registry.agents[...]`
object, mutated in place), `ObserveRequest.client`/`.repository_root`.
None of these can come from a JSON request body directly.

## Decision

**A new `webui/api/` subpackage**, not files bolted onto `webui/routes/`.
The HTML routes depend on `get_templates`/Jinja2 and must stay
behaviorally unmodified — a parallel package makes "purely additive" an
auditable directory boundary rather than a convention to remember, while
staying inside `webui/` since everything shares one `FastAPI` app instance
and `webui/context.py`'s existing `Depends()` accessors.

**`webui/api/translate.py` is the one place JSON-safe knobs become live
objects, shared by every write route.** `build_evaluation_request()`,
`build_gate_request()`, `build_llm_client()`/`build_agent_run_request()` —
called once each by `evaluations.py`/`gates.py`/`agent_runs.py`, and again
by `cycles.py` for each item in its request lists, so a full-cycle
composition never duplicates a single line of translation logic.

**Judgment call: `context_policy` is a required, fully caller-supplied
JSON body, not a hidden server default.** There is no canonical default
`ContextPolicy` anywhere in `metamodel-registry/` — the only precedent
(`scripts/record_agent_fixtures.py`) hand-constructs one ad hoc. Since
`ContextPolicy` is a real `MetamodelEntity`, and its fields meaningfully
change what an agent run can do, hard-coding a value in the server would
silently constrain every caller with no way to override it short of a code
change — the same reasoning `EvaluationRequest.observed_values`/
`GateRequest`'s caller-supplied fields already apply ("never a literal").

**Judgment call: `tool_executor` is never a request field.**
`build_agent_run_request()` hard-codes `SimulatedToolExecutor()` — no
knob, no override — matching every prior phase's "all tools simulated"
discipline exactly.

**Judgment call: OBSERVE is excluded from `POST .../cycles`, explicitly,
not silently dropped.** `ObserveRequest.repository_root` is only
meaningful as a directory the *server process* can see. With zero
authentication in front of a read-write API, accepting an arbitrary path
from a remote, unauthenticated caller is a real filesystem-access-boundary
risk, materially different in kind from `docs/web-ui.md`'s "no
register-project route" gap (that one was a missing *feature*; this one is
a missing *boundary*). `CycleReport.discovery` is always `None` through
this API; discovery stays `scripts/`-driven only.

**Judgment call: `ChecklistOutcome` is accepted uncritically in the
gate-assess endpoint**, matching `GateRequest`'s own existing shape
exactly — not recomputed or verified against `evaluate_checklist()`. A
caller can submit an internally-inconsistent or fabricated
`ChecklistOutcome`. The alternative (accept raw `ChecklistItemResult`s,
call `evaluate_checklist()` server-side) is more defensible but requires
resolving the real `Checklist`/`ChecklistItem` catalog objects per key —
real extra plumbing for a real trust improvement, deferred to a future
phase, not rejected outright.

**Decision, verified not assumed: exception handlers must branch on path
prefix, not be duplicated per exception type.** FastAPI dispatches
`add_exception_handler` by exception *type*; since `UnknownProjectError`
(etc.) can be raised from both an HTML route and an `/api/*` route, one
handler per type is registered, and that handler checks
`request.url.path.startswith("/api/")` to choose `error.html` vs. a JSON
envelope. This is the concrete resolution to "add JSON handlers alongside
the HTML ones" — verified against `webui/app.py`'s real, current shape
before designing this, not assumed to already support dual dispatch.

**Decision, verified not assumed: response serialization needs no new
code.** `CycleReport`/`AgentRunOutcome`/`EvaluationOutcome`/`AgentRunReport`
are plain dataclasses nesting Pydantic models and enums. A live smoke test
against the installed FastAPI version, run before committing to this
design, confirmed dataclass return-type annotations serialize correctly —
nested `EntityRef`, enums, lists — with zero `response_model=` and zero
custom encoder.

**One small, defensive addition found during testing, not anticipated in
the original design:** a `KeyError` handler → 404. `run_suite()`'s
`registry.evaluation_suites[request.suite_key]` (and similar raw
dict-lookups elsewhere) raise a bare `KeyError` for an unrecognized key
that `translate.py`'s own named checks don't already catch (e.g. an
unknown `suite_key`, as opposed to `advance_agent_key`, which *is*
translated). Found by a failing test
(`test_api_evaluations.py::test_unknown_suite_key_is_a_clean_404_not_a_crash`),
not by inspection — fixed with the smallest correct addition (one more
row in the exception-to-status-code table), not routed around.

## Consequences

**Good.** Every write path `orchestrator`/`agent_runtime` left as a plain
Python function call now has a real HTTP caller. The four `GateState`
honesty-gap fields are finally populatable by something other than a unit
test. `webui/graph_discovery.py` factors out the one traversal loop both
the HTML and JSON project-graph views now share, closing a
would-have-been duplication before it existed.

**Costs, stated honestly.** No authentication anywhere — a materially
bigger real-world risk than Phase 8's read-only gap, named as such, not
with the same boilerplate line. `ChecklistOutcome` is a trust gap by
design. OBSERVE/discovery has no HTTP path at all. No run-history
persistence — every POST response is exactly as transient as the Python
object it wraps.

## Alternatives rejected

**A second process/app for the API**, independently deployable from
`webui/`. Rejected per the user's explicit same-process answer; doubles
the wiring (two `create_app()`-style factories, two run scripts) for a
platform with no deployment story yet.

**A fixed default `ContextPolicy`** baked into the server. Rejected —
"never a literal," the same discipline the rest of this codebase already
applies to caller-supplied scoring/state inputs.

**Recomputing `ChecklistOutcome` server-side** from raw item results via
`evaluate_checklist()`. Deferred, not rejected outright — more correct,
more plumbing, a real future-phase candidate.

**Accepting `repository_root` on `POST .../cycles`** to support OBSERVE
over HTTP. Rejected — an unauthenticated, remote-caller-supplied
filesystem path is a real access-boundary risk this phase's own "no auth"
gap makes concrete, not hypothetical.
