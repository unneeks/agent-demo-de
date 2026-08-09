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

## Status: Phase 1–8 — Dual-Twin Metamodel Foundation + Project Graph Service + Discovery + Marketplace + Evaluation Harness + Project Orchestrator + Agent Runtime + Web UI

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
directly in-process — no separate API layer, no browser-triggered write.
Still no API Gateway — the only layer left `(later)`.

| Delivered | |
|---|---|
| 68 entity types | 12 technical · 24 delivery · 32 shared |
| 64 relationship types | 19 of them **cross-twin joins** |
| Four-state provenance | plus document provenance and the inferred-cannot-block rule |
| Four-level role chain | DeliveryRole → Responsibility → EngineeringRole → Agent |
| YAML registries | capabilities (both kinds), the role chain, relationships, platforms, approvals, the marketplace catalog, the evaluation catalog |
| A worked delivery model | 9 phases · 13 tasks · 6 checklists · 28 items · 10 criteria · 6 gates |
| Five deterministic engines | context assembly · checklist + gate readiness · dual impact + traceability · marketplace composition · evaluation harness |
| Two-plane persistence | PostgreSQL (state) + Neo4j (traversal), behind ports |
| `ProjectGraphService` | registry-validated ingestion, dual-plane consistency, snapshot/restore, project-scoped query facade (4 methods) — [`docs/project-graph.md`](docs/project-graph.md) |
| Discovery | uniform agent-based extraction, code + Markdown, two live backends (Anthropic, Copilot CLI) behind one `ExtractionClient` Protocol — [`docs/discovery.md`](docs/discovery.md) |
| Marketplace | 14 skills · 7 tools · 5 knowledge packs · 6 worked agents; pure role/agent composition reusing `EngineeringRole.is_satisfied_by()` — [`docs/marketplace.md`](docs/marketplace.md) |
| Evaluation harness | 2 worked suites (8 metrics, 6 scenarios), closes a real dangling gate reference, gates `Agent` CANDIDATE→EVALUATED→CERTIFIED — [`docs/evaluation.md`](docs/evaluation.md) |
| Project orchestrator | `run_cycle()` composes OBSERVE→IMPACT→STAFF→EVALUATE→GATE, writes `IMPLEMENTED_BY`/`Evaluation`+`EVALUATES`, wires `GateState.traceability` — [`docs/orchestrator.md`](docs/orchestrator.md) |
| Agent runtime | `run_agent()`: a real multi-turn planner-executor loop, 2 live LLM backends + 1 replay behind `AgentLLMClient`, 1 simulated `ToolExecutor` covering all 7 catalog tools, approval-gated `LOW_RISK_WRITE` — [`docs/agent-runtime.md`](docs/agent-runtime.md) |
| Web UI | server-rendered, read-only dashboard, 6 routes, in-process against `ProjectGraphService`/`MetamodelRegistry`, zero writes — [`docs/web-ui.md`](docs/web-ui.md) |
| 79 JSON Schema artifacts | committed, with a drift check |
| 682 tests | 592 unit with the `web` extra installed (576 unit, 6 skipped cleanly without it) |

---

## Quick start

```bash
cd agentic-data-engineering
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python scripts/validate_registries.py     # registries + the worked delivery model
python scripts/export_schemas.py --check  # JSON Schema drift check
pytest tests/unit -q                      # 576 tests, zero infrastructure (webui tests skip cleanly)
pytest tests/contract -q                  # in-memory adapters; real stores skip
```

To exercise the adapters against real databases:

```bash
docker compose up -d
pytest tests/contract -q                  # same assertions, now on Neo4j + PostgreSQL
```

To run the read-only Web UI dashboard, install the `web` extra:

```bash
pip install -e ".[web]"
pytest tests/unit -q                      # 592 tests, webui routes included
python scripts/run_web.py --seed-demo-project   # http://127.0.0.1:8000
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
schemas/                   79 generated JSON Schema artifacts, committed
persistence/               ports.py + memory/ + neo4j/ + postgres/
engines/context/           Deterministic context assembly
engines/gates/             Checklist evaluation and gate readiness
engines/impact/            Dual impact analysis and traceability
engines/composition/       Marketplace role/agent resolution
engines/evaluation/        Evaluation harness: run a suite, gate the agent lifecycle
project_graph/             ProjectGraphService: lifecycle, snapshotting, query facade
discovery/                 Uniform agent-based extraction: walk, resolve, orchestrate, extraction/
orchestrator/              run_cycle(): composes discovery, impact, composition, evaluation, agent runs, gates
agent_runtime/             run_agent(): multi-turn loop, LLM backends, simulated tool execution, approval gating
webui/                     create_app(): read-only Web UI, 6 routes, in-process, no writes
scripts/                   validate_registries.py, export_schemas.py, record_extraction_fixtures.py, record_agent_fixtures.py, run_web.py
docs/                      Architecture, metamodel spec, delivery model, graph model, project graph, discovery, marketplace, evaluation, orchestrator, agent runtime, web UI
tests/unit/                No infrastructure needed (webui tests skip without the web extra)
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

## Next phase

Phase 8 is complete: `webui/`'s `create_app()` is a server-rendered,
read-only dashboard — six `GET` routes, each calling one or two existing
methods on `ProjectGraphService`/`MetamodelRegistry`/a persistence port/
`orchestrator.gate.assess_gate_readiness()` directly in-process, and
rendering the real returned object with Jinja2. No separate API layer, no
JS frontend, no browser-triggered write anywhere. `/projects/{id}` reuses
`ProjectGraphService.snapshot()`'s exact traversal shape, read-only. The
gate-readiness view surfaces a real honesty finding verified against
`engines/gates/readiness.py`: because four of `GateState`'s six dimensions
have no real assembler anywhere in this codebase, a live-computed 100% or
0% for any of them is never a verified finding — the page says so with an
unconditional banner, not a per-score caveat. See
[`docs/web-ui.md`](docs/web-ui.md) and
[ADR-0018](docs/adr/0018-web-ui.md).

Still open, deliberately: **API Gateway is now the only layer
`docs/architecture.md`'s layered diagram still marks `(later)`** — no
`/api/*` route, no JSON endpoint, nothing programmatic can call this
platform; no cycle/agent-run history (`CycleReport`/`AgentRunReport` stay
exactly as transient as Phase 7 left them); no authentication or
authorization; no real-time updates; no pagination; any real tool side
effect, ever; any live human-in-the-loop approval mechanism;
`WORKFLOW_DRIVEN`/`EXTERNAL_AGENT` execution; multi-agent coordination;
scheduled/daemon execution; and four of `GateState`'s six fields
(`present_artifact_kinds`, `checklist_outcomes`, `satisfied_evidence`,
`approvals`) still remain caller-supplied by design — artifact/evidence/
approval detection is its own, larger future phase. Nothing beyond this
foundation should be built until it is reviewed.
