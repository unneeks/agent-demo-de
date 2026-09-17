# Agentic Data Engineering Evolution Platform

This directory is its own project inside a multi-project repo — conventions
here are scoped to this subtree, not the rest of `agent-demo-de`.

## Orient yourself before changing anything

1. `README.md` — status line, "Delivered" table, layout, test counts.
2. `docs/architecture.md` — the dual-twin metamodel, the layered view, the engines table.
3. `docs/adr/README.md` — the index of every decision made, in order, with "Deferred, and why."
4. The specific `docs/<topic>.md` for whatever you're touching, and its paired ADR.

If you're about to explain a design choice from memory instead of pointing at
a file, stop — either it's already written down somewhere in `docs/`, or it
needs to be before you go further.

## House rules (established over many sessions — keep following them)

- **Every nontrivial change gets a doc + an ADR.** `docs/<name>.md`
  (Context / "the one idea that must not be compromised" / worked example /
  errors table / "what this is not") and `docs/adr/NNNN-<name>.md` (Context →
  Decision → Consequences → Alternatives rejected). An ADR with an empty
  alternatives section usually means the decision wasn't really made.
- **Plan mode for anything non-trivial.** Verify claims against the actual
  source before committing to a plan — don't design against a remembered or
  assumed shape of the code.
- **Ask, don't assume, on real scoping decisions** (`AskUserQuestion`) —
  e.g. "caller-supplied only" vs "also infer automatically," "wire into the
  existing loop" vs "standalone."
- **Pure engines, I/O orchestrators.** `engines/*` never touches
  `ProjectGraphService` or any persistence port — no I/O, no LLM calls, unit
  testable in milliseconds. `orchestrator/*` is where real project data gets
  fetched and written. Don't blur this boundary.
- **Never a literal for caller-supplied business data.** Things like
  `desired_maturity`, `ContextPolicy` — no invented defaults. Internal
  calibration constants (a fixed confidence score for a coarse inference, a
  `discovered_by` tag) are fine and different from this.
- **Check the actual blast radius before a signature change.** `grep` every
  call site before assuming a new required parameter is needed — more than
  once, a "this looks required" turned out to already be reachable through an
  existing dependency (see ADR-0021 vs. `orchestrator/gate.py`'s precedent).
- **Additive, not rewriting.** Prefer extending an existing function with an
  optional parameter over branching its behavior; leaving the default
  unchanged should reproduce old behavior byte-for-byte, and that's usually
  worth a regression test that says so explicitly.
- **Commits only on explicit approval**, pushed to the branch already tracked
  by the open PR — check whether a PR already exists before opening a new one.

## Environment

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"     # core + pytest
pip install -e ".[web]"     # + Web UI / API Gateway (fastapi, uvicorn, jinja2, httpx)
pip install -e ".[agent]"   # + live Anthropic backend for the agent runtime
pip install -e ".[neo4j]"   # + real Neo4j adapter
pip install -e ".[postgres]" # + real PostgreSQL adapter
```

## Verify before committing anything

```bash
python scripts/validate_registries.py --quiet   # registries + the worked delivery model
python scripts/export_schemas.py --check         # JSON Schema drift check
pytest tests/unit -q                             # zero infrastructure needed
pytest tests/contract -q                          # in-memory adapters; real stores skip cleanly
pytest tests/integration -q                       # live backends; skips cleanly without credentials
```

For the contract suite against real databases: `docker compose up -d` first.

## Current state (as of the last session)

- Active branch: `claude/agentic-data-engineering-platform-4kjmgt` → PR #13
  (open, against `main`).
- A second branch/PR exists for a separate, parallel effort: Phase 10
  (Marketplace Foundry) on `claude/marketplace-foundry` → PR #14. Check
  `docs/adr/README.md` on each branch — the two have independent ADR
  numbering histories and will conflict if merged carelessly without
  reconciling ADR numbers.
- `git log --oneline -10` and `git status` first, in any new session, before
  touching code.

## Switching between sessions/machines without losing anything

- A decision only survives if it's in an ADR/doc — chat history and
  plan-mode plans are session-local and don't travel.
- Never leave two fronts open at once: commit + push before switching from
  one working copy (local, a web session, another agent) to another.
- The PR description and `docs/adr/README.md`'s index are the durable
  "what's actually shipped" sources of truth.
