# ADR-0022: Interactive onboarding script over existing composition, not new engine code

**Status:** Accepted · **Date:** 2026-08-10 · **Phase:** —

## Context

Every step required to onboard a real (non-demo) project already existed
as real code — `ProjectGraphService.register_project()`
(`project_graph/service.py`), `discover_project()`
(`discovery/orchestrate.py`), `run_cycle()` (`orchestrator/cycle.py`) — but
nothing composed them into one guided entry point the way
`scripts/run_web.py` composes the Web UI. A user asking "how do I onboard
a project" had to be walked through the four docs
(`project-graph.md`/`discovery.md`/`api-gateway.md`/`orchestrator.md`)
individually and write the calling code themselves.

**Scope, per explicit user decisions:**

1. **Implementation:** a Python interactive script
   (`scripts/onboard_project.py`), matching `run_web.py`'s house
   convention, not a bash wrapper — rejected explicitly because a shell
   script fights this codebase's typed entity construction (`Project`,
   `ObserveRequest`, `GateRequest`, ...) awkwardly.
2. **Discovery:** always attempts live extraction, no skip option. The
   script hard-requires `ANTHROPIC_API_KEY` or the GitHub Copilot CLI
   (`copilot`/`gh`) on `PATH` and exits 1 naming both options if neither
   is available.
3. **Delivery model:** reuses whatever `DeliveryModel`(s) the registry
   already loaded (today, only the worked `data-engineering.yaml`) rather
   than requiring the user to author a new one as a onboarding
   prerequisite.
4. **Backend:** offers real Postgres+Neo4j via `docker compose up -d`
   (state persists after the script exits, using the same dev credentials
   `docker-compose.yml` already documents), falling back to the in-memory
   adapters `run_web.py --seed-demo-project` already uses if declined or
   unreachable.

**A finding confirmed live while building this:** a raw extraction-call
failure (as opposed to a malformed-*response* failure, which
`discover_project`'s own `on_error="collect"` already catches via
`parse_response.py`) propagates uncaught through `run_cycle()` — verified
by running the script against this repository itself with the Copilot CLI
backend, which really did raise `discovery.extraction.errors
.ExtractionError` for exactly the reason `copilot_cli_client.py`'s own
docstring already flags (non-interactive JSON output is unverified for
that CLI). This is a real, pre-existing gap in `discover_project`/
`run_cycle`'s own error-collection boundary, not something introduced
here, and fixing it is out of this ADR's scope — see Consequences.

## Decision

**`scripts/onboard_project.py` composes; it invents nothing new in the
domain/engine layers**, mirroring `orchestrator.run_cycle()`'s own stated
discipline for itself. The script:

- Prompts for (or accepts as flags) a backend choice, a `DeliveryModel`
  key, an extraction backend, `Project` fields, discovery inputs
  (`repository_root`/`repository_id`), an optional
  `GapAnalysisRequest.desired_maturity`, and an optional `GateRequest`.
- Builds one `ObserveRequest` and calls `run_cycle(service, registry,
  delivery_model, project_ref, metadata, observe=..., gap_analysis=...,
  gates=[...], on_error="collect")` — a single real call, not a
  hand-rolled re-implementation of what `run_cycle` already composes
  (GAP ANALYSIS → OBSERVE → APPROVAL GATE, in this walkthrough's case;
  `change`/`agent_run_requests`/`evaluation_requests` stay `None` — no
  prior change or measured evaluation exists yet during onboarding).
- Prints the real `CycleReport`, reusing `GateReadiness.render()`
  (`engines/gates/readiness.py`) for gate output rather than re-deriving
  a display format.
- Optionally launches `webui.app.create_app()` in-process against the
  *same* `metadata`/`graph` instances just populated — required for the
  in-memory backend, where a second process would start empty.

**Three pure helpers are factored out** (`_parse_str_set`,
`_project_from_answers`, `_find_extraction_backend`) so the one genuinely
testable logic — comma-set parsing, `Project` construction from already-
collected strings, and the "which backend, given what's available"
decision — has unit coverage
(`tests/unit/test_onboard_project_script.py`) without mocking `input()`
or any live extraction/database call.

**The uncaught-`ExtractionError` boundary gap is handled at the script's
own boundary, not inside `discover_project`/`run_cycle`.** `main()` wraps
the `run_cycle()` call in `try/except ExtractionError`, printing a clear
diagnostic and exiting 1 instead of a raw traceback. This is the CLAUDE.md
"validate only at system boundaries" rule applied literally: the script is
the boundary between a human running a command and an internal composed
call, so it is the right (and only newly-touched) place to catch this —
`orchestrator/cycle.py` and `discovery/orchestrate.py` are unmodified.

## Consequences

**Good.** Onboarding is now one command with prompts instead of four docs
and hand-written glue code. Every flag mirrors a prompt, so the same
script is both a guided walkthrough and a scriptable/CI-usable tool with
no behavioral fork between the two modes.

**Costs, stated honestly.** The walkthrough cannot run fully offline —
discovery being mandatory means a user without `ANTHROPIC_API_KEY` or the
Copilot CLI cannot onboard a project this way at all, only through the
lower-level calls this script wraps. `checklist_outcomes` (a
`dict[str, ChecklistOutcome]`) is left un-promptable — the walkthrough
demonstrates gate assessment's mechanism, not full data-entry for it; a
caller wanting real per-item checklist results still needs `POST
/api/projects/{id}/gates/{key}/assess`.

**Risk accepted, confirmed live rather than assumed.** The GitHub Copilot
CLI backend's non-interactive JSON-output guarantee remains unverified
(ADR-0013's own stated risk) — this script does not fix that, it only
fails cleanly instead of crashing when it happens. Anyone choosing the
Copilot CLI backend for real onboarding should expect this failure mode
until that underlying adapter is hardened, which is separate work.

## Alternatives rejected

**A bash wrapper shelling out to `python -c` snippets**, considered as the
thinner option. Rejected — this codebase's `Project`/`ObserveRequest`/
`GateRequest`/`GapAnalysisRequest` are typed Pydantic/dataclass
constructions; a shell script would either flatten them into fragile
positional CLI args or shell out to Python anyway, at which point writing
Python directly is strictly simpler and matches `run_web.py`'s existing
convention.

**Making discovery skippable**, so the walkthrough could run with zero
live-backend prerequisites. Rejected per explicit user choice — an
onboarding walkthrough that leaves the graph empty defeats its own
purpose; the four-way (backend / delivery-model / discovery /
gap-analysis+gate) scoping conversation happened before implementation
specifically to settle this rather than guess.

**Requiring the user to author a new `DeliveryModel` YAML as part of
onboarding.** Rejected — no tooling for authoring a `delivery-models/
*.yaml` exists anywhere in this codebase yet; inventing an interactive
YAML author inside this script would be new engine-adjacent surface area
this ADR's scope was never meant to cover. The script instead lists and
reuses whatever the registry already loaded, staying purely compositional.

**Fixing `discover_project`'s uncaught-`ExtractionError` boundary gap
inside `discovery/orchestrate.py` itself,** so every caller benefits, not
just this script. Considered once the gap was found live. Rejected for
this ADR — changing an existing, tested function's error-handling
contract is a real behavioral change with its own blast radius (every
existing caller of `discover_project`/`run_cycle`, including
`tests/integration`'s worked examples) that deserves its own scoped
review, not a drive-by fix bundled into an unrelated onboarding-script
ADR. Caught at this script's own boundary instead, which is sufficient for
what this script needs and changes nothing else's behavior.
