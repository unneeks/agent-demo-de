# Architecture

## What this system is

A virtual engineering organization attached to an existing data engineering
project. It reads the project as it actually is — *and reads how the
organization actually delivers changes to it* — then works out what engineering
functions are needed, staffs them with agents, proves those agents are fit
before trusting them, and keeps validating changes against both dimensions.

Operating modes, in adoption order:

| Mode | Behaviour |
|---|---|
| **Assisted** | Agents analyse and recommend. Humans approve everything consequential. |
| **Supervised autonomous** | Agents execute pre-approved low-risk actions within policy. |
| Autonomous | Only certified actions execute automatically. Out of MVP scope. |

## The dual twin

```
                        PROJECT DIGITAL TWIN
                                 │
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
      TECHNICAL TWIN                          DELIVERY TWIN
   what has been built                 how the org governs change
              │                                     │
   Code · Pipelines · Assets            Phases · Tasks · Contracts
   Schemas · Infra · Tests              Checklists · Gates · Approvals
   Architecture · Changes               Standards · Controls · Evidence
              │                                     │
              └──────────────────┬──────────────────┘
                                 ▼
                          ONE PROJECT GRAPH
```

The two dimensions are **not** separate models. One `EntityType` enum, one
`Relationship` type, one provenance model, one graph plane, one metadata plane.
20 of the 67 relationship types are cross-twin joins, and they are what make the
whole thing worth building. See ADR-0008.

## Layered view

```
                        Web UI                       (Phase 8)
                          │
                     API Gateway                     (Phase 9)
                          │
                 Project Orchestrator                (Phase 6)
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   Marketplace      Composition        Evaluation
    Service          Engine              Harness
    (later)         (Phase 4)           (Phase 5)
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                   Agent Runtime                     (Phase 7)
                          │
   ╔══════════════════════╧══════════════════════╗
   ║       PROJECT GRAPH SERVICE  (Phase 2)      ║
   ║   lifecycle · dual-plane writes · snapshot  ║
   ║   query facade over the engines below       ║
   ╠═════════════════════════════════════════════╣
   ║      ENGINES  (Phase 1, composition P4)     ║
   ║  context · gates · impact + traceability    ║
   ║  composition -- role/agent resolution       ║
   ║  foundry -- mining, pattern discovery (P10) ║
   ╠═════════════════════════════════════════════╣
   ║          METAMODEL  (Phase 1)               ║
   ║   dual twin · relationships · provenance    ║
   ║   registries · delivery model               ║
   ╠═════════════════════════════════════════════╣
   ║   PostgreSQL              Neo4j             ║
   ║   metadata plane          graph plane       ║
   ╚═════════════════════════════════════════════╝
```

Everything above the double line is replaceable. Everything at and below it is
the platform. The project graph service does not widen what's replaceable — it
is a thin front door onto the same ports, not a new layer of infrastructure.

Marketplace Foundry (Phase 10) reads through the same Project Graph Service
every other consumer does, but is not a Project Orchestrator step and is not
drawn in the vertical chain above it — it is triggered independently, any
time a project's graph already exists, via `scripts/run_foundry.py`. See
[`docs/marketplace-foundry.md`](marketplace-foundry.md).

## The two storage planes

| | **PostgreSQL — metadata plane** | **Neo4j — graph plane** |
|---|---|---|
| System of record for | entity **state** | relationship **traversal** |
| Holds | versioned rows (both twins), relationship log, gate assessments, checklist outcomes, audit ledger | the dual twin: nodes and provenanced edges |
| Answers | "what is this contract's configuration?" | "what breaks, and what does the process now require?" |
| Rebuildable? | No — the durable copy | **Yes**, by projection |

Nodes are keyed by `(entity_type, entity_id)` and carry no version. A node is
the *thing*; versioned state lives in PostgreSQL. See ADR-0001.

## The engines

Each is a pure function. None calls an LLM. That is what makes them unit
testable in milliseconds and replayable after the fact. (Phase 1 shipped the
first four; `engines/gap_analysis/` closes ADR-0021's deferred half of the
Composition Engine; `engines/foundry/` is Phase 10's mining/pattern-discovery
half of Marketplace Foundry, ADR-0022 — its one LLM step lives in
`foundry/synthesis/`, outside this package.)

| Engine | Input | Output |
|---|---|---|
| **Context** (`engines/context/`) | policy + candidates | ordered bundle, drop reasons, stable hash |
| **Gates** (`engines/gates/`) | gate + observed state | per-dimension scores, PASS/CONDITIONAL/BLOCKED, blockers |
| **Impact** (`engines/impact/`) | change + graph + delivery model | technical blast radius **and** delivery obligations; traceability chains |
| **Composition** (`engines/composition/`) | engineering role + agent catalog | matches, near-misses, itemized gaps (Phase 4); delivery conformance (ADR-0020) |
| **Gap Analysis** (`engines/gap_analysis/`) | observed + desired capability maturity | itemized `CapabilityGap`s, recommended engineering roles (ADR-0021) |
| **Foundry** (`engines/foundry/`) | mined observations | recurring patterns, candidate completeness scores (Phase 10; `foundry/synthesis/` layers one LLM call on top, independently invoked) |

## The organization model

```
Problem ──REQUIRES──▶ Capability ─┐
                                  ├─REALIZED_BY──▶ EngineeringResponsibility
Problem ──REQUIRES──▶ DeliveryCapability ─┘                  │
                                                        FULFILLED_BY
DeliveryRole ──ACCOUNTABLE_FOR──▶ EngineeringResponsibility  ▼
   (who answers                                        EngineeringRole
    in the org)                                             │
                                                      IMPLEMENTED_BY
                                                            ▼
                                                          Agent
                                          ┌─────────────────┼──────────────────┐
                                      HAS_SKILL        USES_TOOL      CONSUMES_KNOWLEDGE
```

Four levels, not two. A delivery role is an organizational accountability that
exists whether or not this platform does; an engineering role is a marketplace
abstraction an agent implements. Naming the responsibility between them is what
lets an organization reshuffle its job titles without invalidating the agent
ecosystem. See ADR-0009.

## The continuous loop

```
OBSERVE → DETECT CHANGE → TECHNICAL IMPACT + DELIVERY IMPACT → UPDATE CONTRACTS
   ▲                                                                 │
   │                                                                 ▼
OBSERVE ← DELIVER ← APPROVAL GATE ← EVALUATE ← COLLECT EVIDENCE ← SELECT AGENTS
                                                              ← RUN CHECKLISTS
                                                              ← RUN TESTS
```

Phase 1 supplies the vocabulary this loop is recorded in and three of the steps
as working code (impact, checklists + gates, context). It does not run the loop.

## How governance is enforced

Governance that cannot be enforced by the pipeline is decorative, so each rule
is structural, and each has a test asserting the violation is refused.

| Rule | Where enforced |
|---|---|
| Inference is never stated as fact | `Provenanced` validator + PostgreSQL `CHECK` |
| **An inferred rule cannot block delivery** | `Blockable` mixin |
| **Semantically extracted facts must name their document** | `Provenanced` validator + `CHECK` |
| Every tool action is classified | `ToolAction.action_class` required, no default |
| High-risk actions need a human | `ToolAction` validator |
| Destructive actions always need two humans | `registry.validate()` |
| **A waiver must carry reason, approver, timestamp and evidence** | `Waiver` + `ChecklistItemResult` |
| **An expired waiver stops counting** | `evaluate_checklist` |
| **A gate requiring nothing is rejected** | `ApprovalGate` validator |
| **An advisory gate can never report BLOCKED** | `assess_gate` |
| **A contract with no controls is rejected** | `DeliveryContract` validator |
| **A non-delegable responsibility may name no engineering role** | `registry.validate()` |
| **Exactly one accountable role per task** | `registry.validate()` |
| **Phase dependency graphs must be acyclic** | `registry.validate()` |
| No production deployment without certification *and* approval | `Deployment` validator |
| Blocking metric failure cannot be outvoted | `Evaluation` validator |
| Trust score is limited by the weaker dimension | `Evaluation.trust_score` |
| No uncited findings | `Finding` validator |
| Conditional approval must state conditions | `Approval` validator |
| Audit ledger cannot be rewritten | hash chain + PostgreSQL `DO INSTEAD NOTHING` |

## What Phase 1 does not do

Document assimilation (§17–18) · marketplace resolution · composition engine ·
agent runtime · any LLM call · evaluation execution · API · UI · autonomous
production writes.

The question this phase answers is narrower: *is there a metamodel precise
enough — across both twins — that the rest can be built on it without being
rewritten?*
