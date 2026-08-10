# Agentic Data Engineering Evolution Platform

A digital engineering twin that models **both** the technical system and the
organizational delivery system, then composes an evidence-backed agent workforce
capable of executing engineering work *within that delivery model*.

The durable intellectual property is the chain:

```
Problem → Capability → Responsibility → Engineering Role → Agent → Skill → Tool
       → Delivery Contract → Checklist → Gate → Evidence → Approval → Deployment
```

Agents are replaceable. The LLM is replaceable. The cloud is replaceable. The
tools are replaceable. The metamodel, the dual twin, the capability graph, the
delivery model and the evidence model are not — so those are what this phase
builds.

---

## Status: Phase 1–10 — Dual-Twin Metamodel Foundation + Project Graph Service + Discovery + Marketplace + Evaluation Harness + Project Orchestrator + Agent Runtime + Web UI + API Gateway + Marketplace Foundry

Phase 1 deliberately contains **no** document assimilation, composition engine,
agent runtime, LLM calls, evaluation *execution*, API or UI. Those concepts are
*modelled*; their engines come later. Phase 2 adds the one thing Phase 1 had no
owner for — a project's twin as a lifecycle. Phase 3 adds the first adapter
layer that turns a real project into real graph state: uniform, agent-based
discovery of code *and* delivery documentation, writing through
`ProjectGraphService`. Phase 4 adds the marketplace: a populated Agent/Skill/
Tool catalog and a pure engine that resolves engineering roles against it.
Phase 5 adds the evaluation harness: a populated evaluation catalog and a pure
engine that scores a suite and gates the agent lifecycle. Phase 6 adds the
project orchestrator: `run_cycle()` ties discovery, impact analysis,
composition and evaluation into one continuous loop over a real project,
closing the write path composition and evaluation had left deferred. Phase 7
adds the agent runtime: a real multi-turn planner-executor loop behind two
live LLM backends (Anthropic, Copilot CLI) plus a hermetic replay backend,
composed into `run_cycle()` as a new opt-in step — every tool call it makes
is answered by a simulated executor, so no real side effect exists anywhere
in this codebase. Phase 8 adds the Web UI: a server-rendered, read-only
dashboard whose six routes call `ProjectGraphService`/`MetamodelRegistry`
directly in-process. Phase 9 adds the API Gateway: read-write `/api/*`
routes in the same process, sharing the same backend — register a
project, ingest entities/relationships, trigger evaluations/gate
assessments/agent runs/full cycles, translating JSON into the same live
objects `orchestrator`/`agent_runtime` already require, server-side only.
Every layer in the layered diagram below is now built. Phase 10 adds
Marketplace Foundry, developed on its own branch/PR as a new,
independently-shippable feature rather than an addition to the sequential
phase line: mine a project's already-ingested graph for recurring
engineering patterns, synthesize candidate Skills/Tools/Agents from them
via an LLM (the one step in the pipeline that calls one, reusing
discovery's own `ExtractionClient` Protocol), and score their structural
completeness — invoked independently, any time, via
`scripts/run_foundry.py`, never wired into `run_cycle()`. Two further
ADR-tracked closures, developed in parallel on the sequential platform
line and merged in here: ADR-0020 wires `DeliveryContract.conformance_of()`
into real composition staffing, and ADR-0021 adds capability gap analysis
— coarse maturity inference plus itemized `CapabilityGap`s, wired into
`run_cycle()` as a new optional step.

| Delivered | |
|---|---|
| 73 entity types | 12 technical · 24 delivery · 37 shared |
| 67 relationship types | 20 of them **cross-twin joins** |
| Four-state provenance | plus document provenance and the inferred-cannot-block rule |
| Four-level role chain | DeliveryRole → Responsibility → EngineeringRole → Agent |
| YAML registries | capabilities (both kinds), the role chain, relationships, platforms, approvals, the marketplace catalog, the evaluation catalog |
| A worked delivery model | 9 phases · 13 tasks · 6 checklists · 28 items · 10 criteria · 6 gates |
| Seven deterministic engines | context assembly · checklist + gate readiness · dual impact + traceability · marketplace composition · evaluation harness · capability gap analysis · Foundry mining/pattern discovery |
| Two-plane persistence | PostgreSQL (state) + Neo4j (traversal), behind ports |
| `ProjectGraphService` | registry-validated ingestion, dual-plane consistency, snapshot/restore, project-scoped query facade (4 methods) — [`docs/project-graph.md`](docs/project-graph.md) |
| Discovery | uniform agent-based extraction, code + Markdown, two live backends (Anthropic, Copilot CLI) behind one `ExtractionClient` Protocol — [`docs/discovery.md`](docs/discovery.md) |
| Marketplace | 14 skills · 7 tools · 5 knowledge packs · 6 worked agents; pure role/agent composition reusing `EngineeringRole.is_satisfied_by()`, plus real `DeliveryContract.conformance_of()` staffing checks (ADR-0020) — [`docs/marketplace.md`](docs/marketplace.md) |
| Evaluation harness | 2 worked suites (8 metrics, 6 scenarios), closes a real dangling gate reference, gates `Agent` CANDIDATE→EVALUATED→CERTIFIED — [`docs/evaluation.md`](docs/evaluation.md) |
| Capability gap analysis | coarse, evidence-counting maturity inference from real `Pipeline`/`Test`/`Evaluation` facts, diffed against caller-supplied desired maturity into itemized `CapabilityGap`s + advisory role recommendations (ADR-0021) — [`docs/gap-analysis.md`](docs/gap-analysis.md) |
| Project orchestrator | `run_cycle()` composes GAP ANALYSIS→OBSERVE→IMPACT→STAFF→EVALUATE→GATE, writes `IMPLEMENTED_BY`/`Evaluation`+`EVALUATES`/`CapabilityGap`+`HAS_GAP`, wires `GateState.traceability` — [`docs/orchestrator.md`](docs/orchestrator.md) |
| Agent runtime | `run_agent()`: a real multi-turn planner-executor loop, 2 live LLM backends + 1 replay behind `AgentLLMClient`, 1 simulated `ToolExecutor` covering all 7 catalog tools, approval-gated `LOW_RISK_WRITE` — [`docs/agent-runtime.md`](docs/agent-runtime.md) |
| Web UI | server-rendered, read-only dashboard, 6 routes, in-process against `ProjectGraphService`/`MetamodelRegistry`, zero writes — [`docs/web-ui.md`](docs/web-ui.md) |
| API Gateway | read-write `/api/*`, same process as the Web UI — register/ingest/relate, trigger evaluations/gate-assessment/agent-runs/cycles — [`docs/api-gateway.md`](docs/api-gateway.md) |
| Marketplace Foundry | mine → discover patterns → LLM-synthesize candidate Skills/Tools/Agents → score structural completeness, `scripts/run_foundry.py` — [`docs/marketplace-foundry.md`](docs/marketplace-foundry.md) |
| 85 JSON Schema artifacts | committed, with a drift check |
| 833 tests | 743 unit with the `web` extra installed (683 unit, 14 skipped cleanly without it) |

---

## Quick start

```bash
cd agentic-data-engineering
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python scripts/validate_registries.py     # registries + the worked delivery model
python scripts/export_schemas.py --check  # JSON Schema drift check
pytest tests/unit -q                      # 683 tests, zero infrastructure (webui tests skip cleanly)
pytest tests/contract -q                  # in-memory adapters; real stores skip
```

To exercise the adapters against real databases:

```bash
docker compose up -d
pytest tests/contract -q                  # same assertions, now on Neo4j + PostgreSQL
```

To run the Web UI dashboard and the `/api/*` gateway, install the `web` extra:

```bash
pip install -e ".[web]"
pytest tests/unit -q                      # 743 tests, webui + API routes included
python scripts/run_web.py --seed-demo-project   # http://127.0.0.1:8000 (UI) and /api/* (JSON)
```

To run discovery against a real project, install the `agent` extra and set an
API key (or have `copilot`/`gh` on `PATH`):

```bash
pip install -e ".[agent]"
export ANTHROPIC_API_KEY=...
pytest tests/integration -q -m agent_integration  # skips cleanly without either backend
```

---

## The two twins are one graph

This is the idea everything else depends on. Not two models that reference each
other — one graph, one `EntityType` enum, one `Relationship` type, one
provenance model.

```
      TECHNICAL TWIN                          DELIVERY TWIN
   what has been built                 how the org governs change

  CodeArtifact                             DeliveryModel
       ↑ DEPENDS_ON                             │ HAS_PHASE
   Pipeline ◀────── GOVERNS ─────── DeliveryTask ── VALIDATED_BY ─▶ Checklist
       ↑ DEPENDS_ON                             │ ENDS_AT_GATE
   DataAsset ◀───── DESCRIBES ── DeliveryArtifact          ApprovalGate
       ↑ COVERS                                                  ▲
     Test ─────────── SATISFIES ─────▶ EvidenceRequirement       │
       │ GENERATES                                               │
    Evidence ─────── SUPPORTS_APPROVAL ─────▶ Approval ──────────┘
                                                  │ AUTHORIZES
                                             Deployment
```

The payoff, from `engines/impact/`:

```
Change PR-482 (risk HIGH)
  Technical impact:
    CodeArtifact:customer_address.sql   (confidence 1.00, depth 0)
    Pipeline:stg_customers              (confidence 1.00, depth 1)
    Pipeline:mart_customer_360          (confidence 1.00, depth 2)
    Test:test_customer_360              (confidence 1.00, depth 3)
  Delivery impact:
    [task]      task.logical-data-model      -- governs a changed technical entity
    [checklist] logical-model-checklist      -- required by task.logical-data-model
    [gate]      gate.data-architecture-review -- task ends at this gate
    [evidence]  ev.logical-model, ev.traceability, ev.checklist-result
    [approval]  data-architect               -- must approve a gate this change must clear
    [artifact]  logical-data-model-v3        -- may now be out of date (confidence 0.70)
```

Note the risk: the change touched one file, but it trips a HIGH-risk gate, so
the change is HIGH risk. Only the delivery twin knows that.

---

## The six ideas worth knowing

### 1. Delivery documentation is executable metadata

A checklist is a structured object with per-item validation methods, not a text
blob. A gate computes readiness across six dimensions and returns
`PASS` / `CONDITIONAL` / `BLOCKED` with itemized blockers:

```
gate.data-architecture-review
  Artifacts        100% OK      Approvals        100% OK
  Checklists       100% OK      Evidence         100% OK
  Evaluations      100% OK      Traceability      87% --
  Overall           97% -> CONDITIONAL
```

### 2. Inference may advise; only verified rules may block

The addendum's warning, made structural. A `Standard`, `Control`, `ApprovalRule`,
`ChecklistItem` or `ApprovalGate` with `INFERRED` provenance **cannot** be
`blocking=True`:

```python
Standard(..., provenance=INFERRED, confidence=0.75, blocking=True)
# ValidationError: a rule with provenance INFERRED cannot be blocking=True.
#   Inferred rules may advise, but only an OBSERVED or human-verified rule may
#   stop delivery -- extracted text must never silently become enforced policy.
```

Extracted rules also carry `source_document`, `source_section` and
`extraction_method`, so a human can check the paragraph the platform read.

### 3. Capability is necessary but not sufficient

`DeliveryContract.conformance_of()` asks both questions:

```
copilot-agent may not execute contract.logical-data-model:
  checklist: logical-model-checklist (required);
  gate: gate.data-architecture-review (required);
  artifact: logical-data-model (required)
```

The agent is *technically capable* and still rejected. That is the difference
between a copilot and a member of an engineering organization.

### 4. Four levels, because roles and accountabilities are not the same thing

```
DeliveryRole ──▶ EngineeringResponsibility ──▶ EngineeringRole ──▶ Agent
```

Both catalogs contain "Data Architect" and they are different objects: the
delivery role also carries `resp.architecture-signoff`, which is marked
`delegable_to_agent: false` and names no engineering role at all. The registry
validator refuses any non-delegable responsibility that names one.

### 5. Evidence over inference

Provenance is structural. `INFERRED` requires a confidence, `OBSERVED` is pinned
to 1.0 and needs a discoverer, `CERTIFIED` needs a named signer. Enforced again
as PostgreSQL `CHECK` constraints, because application validation is bypassable.

### 6. Context is governed, and delivery-aware

Assembly is a pure, LLM-free function: same inputs and policy version yield an
identical `bundle_hash`, and every excluded candidate is recorded with a reason.
With `require_delivery_context`, the controls an agent will be judged against
are pinned — and if they cannot fit the budget the assembler *raises* rather
than dropping them.

---

## Layout

```
domain/metamodel/          Entities (both twins), relationships, registry, versioning
metamodel-registry/        Versioned YAML vocabularies + the worked delivery model
schemas/                   85 generated JSON Schema artifacts, committed
persistence/               ports.py + memory/ + neo4j/ + postgres/
engines/context/           Deterministic context assembly
engines/gates/             Checklist evaluation and gate readiness
engines/impact/            Dual impact analysis and traceability
engines/composition/       Marketplace role/agent resolution
engines/evaluation/        Evaluation harness: run a suite, gate the agent lifecycle
engines/gap_analysis/      Coarse capability maturity inference + gap diff (ADR-0021)
engines/foundry/           Pure mining, pattern discovery, candidate completeness scoring, candidate lifecycle
project_graph/             ProjectGraphService: lifecycle, snapshotting, query facade
discovery/                 Uniform agent-based extraction: walk, resolve, orchestrate, extraction/
orchestrator/              run_cycle(): composes gap analysis, discovery, impact, composition, evaluation, agent runs, gates
agent_runtime/             run_agent(): multi-turn loop, LLM backends, simulated tool execution, approval gating
webui/                     create_app(): read-only HTML dashboard (routes/) + read-write JSON API (api/)
foundry/                   run_foundry_cycle(): mine -> discover -> LLM-synthesize -> evaluate, synthesis/ reuses discovery's ExtractionClient
scripts/                   validate_registries.py, export_schemas.py, record_extraction_fixtures.py, record_agent_fixtures.py, run_web.py, run_foundry.py
docs/                      Architecture, metamodel spec, delivery model, graph model, project graph, discovery, marketplace, evaluation, orchestrator, agent runtime, web UI, API gateway, gap analysis, marketplace foundry
tests/unit/                No infrastructure needed (webui/API tests skip without the web extra)
tests/contract/            One contract, run against every adapter
tests/integration/         Live discovery + agent backends, independently skippable
```

Start with [`docs/architecture.md`](docs/architecture.md), then
[`docs/delivery-model.md`](docs/delivery-model.md). Decisions are in
[`docs/adr/`](docs/adr/).

---

## Development

```bash
python scripts/export_schemas.py          # after changing any model
python scripts/validate_registries.py     # after editing metamodel-registry/
```

Changing an entity without regenerating schemas fails `tests/unit/test_schemas.py`.
Bumping `METAMODEL_VERSION` without updating the registry fails
`tests/unit/test_registries.py`.

## Status of the layered diagram

Phase 9 is complete: `webui/api/`'s `/api/*` routes are a read-write JSON
gateway, mounted in the same `FastAPI` app `webui/routes/`'s dashboard
already uses — register a project, ingest entities/relationships, trigger
an evaluation run, trigger a gate assessment with **caller-supplied**
`GateState` inputs (the one place those four honesty-gap fields become
real), trigger an agent run, trigger a full `run_cycle()`. Every write
translates JSON into the same live Python objects `orchestrator`/
`agent_runtime` already require — never a client-supplied `ToolExecutor`/
`AgentLLMClient`/filesystem path. See [`docs/api-gateway.md`](docs/api-gateway.md)
and [ADR-0019](docs/adr/0019-api-gateway.md).

Phase 10, Marketplace Foundry, is complete on its own branch/PR: given a
project's already-ingested graph, `engines/foundry/mining.py` and
`discovery.py` deterministically mine `EngineeringObservation`s and group
them into `EngineeringPattern`s (no LLM, exact-match grouping plus
set-overlap similarity — crude and honestly labelled as such), then
`foundry/synthesis/` calls an LLM exactly once per pattern per requested
candidate kind to author a `CandidateSkill`/`CandidateTool`/`CandidateAgent`
proposal's descriptive content — reusing `discovery/extraction/`'s
`ExtractionClient` Protocol unmodified, the platform (never the LLM)
still assigning candidate identity and provenance. `engines/foundry/
evaluation.py` scores each candidate's structural completeness through
the real, unmodified evaluation harness. Positioned beside Composition/
Evaluation in the layered diagram, reading from Project Graph Service the
same way they do, but **independently invoked** — `scripts/run_foundry.py`,
never a `run_cycle()` step. See [`docs/marketplace-foundry.md`](docs/marketplace-foundry.md)
and [ADR-0020](docs/adr/0020-marketplace-foundry.md).

**Every layer `docs/architecture.md`'s layered diagram names is now
built**, `(later)` next to none of them. That does not mean the platform
is production-ready — it means the *architectural skeleton* is complete.
Still open, deliberately, at the platform level, consolidated across every
phase's own named gaps: **no authentication or authorization anywhere** —
every write endpoint (`webui/api/`) is reachable by anyone who can reach
the process; no real tool side effect, ever (`agent_runtime` always
simulates); no live human-in-the-loop approval mechanism
(`AutomationLevelApprovalPolicy` is a synchronous, caller-declared,
simulated check); no `WORKFLOW_DRIVEN`/`EXTERNAL_AGENT` execution; no
multi-agent coordination; no scheduled/daemon execution; no OBSERVE/
discovery over HTTP; no rate limiting; no cycle/agent-run history
persistence; no deployment story (containerization, secrets, TLS); and
four of `GateState`'s six fields (`present_artifact_kinds`,
`checklist_outcomes`, `satisfied_evidence`, `approvals`) remain
caller-supplied by design outside the one gate-assess endpoint that lets a
caller populate them — full artifact/evidence/approval *detection* is its
own, larger future phase. Nothing beyond this foundation should be built
until it is reviewed.

Marketplace Foundry adds its own, separately scoped non-goals, named in
full in [`docs/marketplace-foundry.md`](docs/marketplace-foundry.md): no
shadow mode or certification workflow beyond a 4-state `CandidateStatus`,
no publish-to-YAML mechanism (a human hand-writes the registry diff from a
`CERTIFIED` candidate's payload), no cross-project/enterprise clustering,
no knowledge-pack/delivery-blueprint synthesis, no continuous-learning
feedback loop, and no raw repo/document re-scanning — it mines only what
`discovery/` already ingested.
