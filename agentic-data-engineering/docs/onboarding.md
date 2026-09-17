# Onboarding a new project

`scripts/onboard_project.py` is a guided, interactive entry point over
existing Phase 1–9 code. Before it existed, onboarding a real (non-demo)
project meant reading `docs/project-graph.md`, `docs/discovery.md` and
`docs/orchestrator.md` and hand-writing a script that called
`ProjectGraphService.register_project()`, `discover_project()` and
`run_cycle()` correctly in order. See
[ADR-0022](adr/0022-onboarding-script.md) for the scoping decisions and the
alternatives rejected.

## The one idea that must not be compromised

**A guided caller of real code paths, not a simulation of them.** Every
step the script prints is a real `ProjectGraphService`/`discover_project()`/
`run_cycle()` call with a real return value — no synthetic success
messages, no step that merely describes what would happen. It composes
existing functions exactly the way `orchestrator.run_cycle()`'s own
docstring insists on for itself: "composes; invents nothing."

## A worked walkthrough

In-memory backend, `ANTHROPIC_API_KEY` set, onboarding a project called
`acme` against a local checkout at `../acme-repo`:

```
$ python scripts/onboard_project.py
Use real Postgres+Neo4j (needs `docker compose up -d` first)? No = in-memory, ephemeral [y/N]: n
Backend: in-memory (state ends when this process exits)
Delivery model: de-delivery-model
Project id: acme
Project name [acme]: Acme Pipelines
Technologies (comma-separated, optional): dbt, snowflake, airflow
Owners (comma-separated, optional): data-platform
Business domain (optional): retail
Criticality (optional): high
Repository root (path to the codebase to scan): ../acme-repo
Repository id [acme-repo]:
Run capability gap analysis? [y/N]: n
Assess a gate now? Enter its key (blank to skip):

Running discovery against /Users/.../acme-repo ...

=== Cycle report ===
Discovery: 14 entities, 9 relationships ingested
  code_artifact         6
  pipeline               4
  data_asset             3
  repository              1
  ...

Launch the Web UI dashboard now against this data? [Y/n]: y
Serving on http://127.0.0.1:8000 -- Ctrl+C to stop.
```

Every prompt has a matching flag (`--project-id`, `--repository-root`,
`--desired-maturity KEY=LEVEL` repeatable, `--gate-key`, ...), so the same
walkthrough runs non-interactively — a flag that's set is never re-prompted.

## Scoping decisions, stated plainly

- **Discovery is mandatory, always live.** There is no skip option — an
  onboarded project with an empty graph defeats the point. The script
  hard-requires `ANTHROPIC_API_KEY` or the GitHub Copilot CLI on `PATH`
  and exits 1 with both options named if neither is available.
- **The delivery model is reused, not authored.** The script lists every
  `DeliveryModel` the registry loaded (today, only the worked
  `data-engineering.yaml`) and lets the caller pick one. It does not walk
  a new project through authoring its own delivery model — that's a
  separate, larger act of registry-YAML authorship, out of scope here.
- **A real backend is offered, not required.** Postgres+Neo4j via
  `docker compose up -d` persists state after the script exits; declining
  (or an unreachable database) falls back to the same in-memory adapters
  `run_web.py --seed-demo-project` uses, which disappear when the process
  exits.
- **Gate assessment is a mechanism demo, not a full data-entry UI.**
  `present_artifact_kinds`/`satisfied_evidence`/`approvals` are simple
  comma-separated sets; `checklist_outcomes` (a `dict[str,
  ChecklistOutcome]`, one entry per checklist item) is left empty on
  purpose, with a printed note pointing at `POST
  /api/projects/{id}/gates/{key}/assess` for real per-item data entry.

## Errors

| Error | Raised when |
|---|---|
| Exit 1, "discovery needs a live extraction backend" | Neither `ANTHROPIC_API_KEY` nor `copilot`/`gh` is available |
| Exit 1, "could not reach Postgres/Neo4j" | `--backend postgres-neo4j` chosen but the databases aren't reachable — prints the `docker compose up -d` hint |
| Exit 1, "repository_root ... does not exist" | The given/prompted path isn't a real directory |
| Exit 1, "discovery's extraction call failed: ..." | The extraction backend's own `.extract()` call raised (e.g. the Copilot CLI's non-interactive JSON output isn't guaranteed — see `discovery/extraction/copilot_cli_client.py`'s own docstring). Caught at this script's boundary since `discover_project`'s `on_error="collect"` only covers malformed-*response* failures, not a raw call failure — confirmed live against the real Copilot CLI while building this script |
| `report.failed` entries, script keeps running | Any other per-step failure `run_cycle()`'s own `on_error="collect"` already collects (a rejected write, an unknown gate key, a bad gap-analysis value) |

## What this is not

- **Not a replacement for `run_cycle()`'s richer optional steps.**
  `agent_run_requests` and `evaluation_requests` aren't surfaced — this is
  an onboarding walkthrough (no prior agent run or measured evaluation
  exists yet to wire in), not a general `run_cycle()` front end.
- **Not a way to author a new `DeliveryModel`.** It selects among what the
  registry already loaded; writing a new `delivery-models/*.yaml` for an
  org with no existing one is a separate, manual act.
- **Not authenticated, not multi-user.** Same boundary every other layer
  in this platform states plainly — see `docs/architecture.md`'s "still
  open" list.
- **Not a guarantee the chosen extraction backend actually returns usable
  output.** Both live backends carry the same unverified-call-shape risk
  ADR-0013 already flagged; this script surfaces the failure cleanly, it
  does not fix it.
