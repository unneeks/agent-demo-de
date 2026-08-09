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

## Status: Phase 1, 2 & 3 — Dual-Twin Metamodel Foundation + Project Graph Service + Discovery

Phase 1 deliberately contains **no** document assimilation, composition engine,
agent runtime, LLM calls, evaluation *execution*, API or UI. Those concepts are
*modelled*; their engines come later. Phase 2 adds the one thing Phase 1 had no
owner for — a project's twin as a lifecycle. Phase 3 adds the first adapter
layer that turns a real project into real graph state: uniform, agent-based
discovery of code *and* delivery documentation, writing through
`ProjectGraphService` — no orchestration, evaluation, or agent runtime yet.

| Delivered | |
|---|---|
| 68 entity types | 12 technical · 24 delivery · 32 shared |
| 64 relationship types | 19 of them **cross-twin joins** |
| Four-state provenance | plus document provenance and the inferred-cannot-block rule |
| Four-level role chain | DeliveryRole → Responsibility → EngineeringRole → Agent |
| YAML registries | capabilities (both kinds), the role chain, relationships, platforms, approvals |
| A worked delivery model | 9 phases · 13 tasks · 6 checklists · 28 items · 10 criteria · 6 gates |
| Three deterministic engines | context assembly · checklist + gate readiness · dual impact + traceability |
| Two-plane persistence | PostgreSQL (state) + Neo4j (traversal), behind ports |
| `ProjectGraphService` | registry-validated ingestion, dual-plane consistency, snapshot/restore, project-scoped query facade — [`docs/project-graph.md`](docs/project-graph.md) |
| Discovery | uniform agent-based extraction, code + Markdown, two live backends (Anthropic, Copilot CLI) behind one `ExtractionClient` Protocol — [`docs/discovery.md`](docs/discovery.md) |
| 79 JSON Schema artifacts | committed, with a drift check |
| 537 tests | 449 unit with zero infrastructure |

---

## Quick start

```bash
cd agentic-data-engineering
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python scripts/validate_registries.py     # registries + the worked delivery model
python scripts/export_schemas.py --check  # JSON Schema drift check
pytest tests/unit -q                      # 449 tests, zero infrastructure
pytest tests/contract -q                  # in-memory adapters; real stores skip
```

To exercise the adapters against real databases:

```bash
docker compose up -d
pytest tests/contract -q                  # same assertions, now on Neo4j + PostgreSQL
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
project_graph/             ProjectGraphService: lifecycle, snapshotting, query facade
discovery/                 Uniform agent-based extraction: walk, resolve, orchestrate, extraction/
scripts/                   validate_registries.py, export_schemas.py, record_extraction_fixtures.py
docs/                      Architecture, metamodel spec, delivery model, graph model, project graph, discovery
tests/unit/                No infrastructure needed
tests/contract/            One contract, run against every adapter
tests/integration/         Live discovery backends, independently skippable
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

Phase 3 is complete: discovery of code *and* delivery documentation (§17–18),
writing through `ProjectGraphService.ingest_entity`/`ingest_relationship`
rather than the raw ports, proven as a worked example against
`../agentic-ai-ollama-demo/`, a real dbt + Python + DuckDB project alongside
this repository — see [`docs/discovery.md`](docs/discovery.md) and
[ADR-0013](docs/adr/0013-agent-based-extraction.md). Nothing beyond this
foundation should be built until it is reviewed.
