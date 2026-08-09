# Architecture Decision Records

Decisions taken in Phase 1, with reasoning and rejected alternatives, so a later
phase can overturn one knowingly rather than by accident.

| ADR | Decision | Why it matters |
|---|---|---|
| [0001](0001-two-plane-persistence.md) | PostgreSQL for state, Neo4j for traversal | Each store does one job well; the graph stays rebuildable and replaceable |
| [0002](0002-hybrid-metamodel-source-of-truth.md) | Pydantic shapes, YAML vocabularies | A whole delivery model is data; entity invariants stay statically checked |
| [0003](0003-provenance-model.md) | Four provenance states plus document attribution | Extracted delivery rules cite the paragraph they came from |
| [0004](0004-relationships-as-first-class-objects.md) | Relationships are objects; the vocabulary is data | Edges carry confidence, which cross-twin inference depends on |
| [0005](0005-capability-platform-indirection.md) | Capability / Platform / TechnologyBinding | Agents reason about capabilities; only bindings name clouds |
| [0006](0006-deterministic-context-assembly.md) | Deterministic, delivery-aware context assembly | Decisions replay; agents are never judged on unseen controls |
| [0007](0007-ports-and-adapters.md) | Ports with an in-memory reference implementation | Fast infrastructure-free tests; genuinely swappable storage |
| [0008](0008-dual-twin-single-graph.md) | **The two twins are one graph** | Cross-twin questions are traversals, not application-level joins |
| [0009](0009-four-level-role-chain.md) | Four-level role chain; inferred rules cannot block | Human accountability stays distinguishable from machine capability |
| [0010](0010-entity-consolidations.md) | Deliberate consolidations vs the specification | Records where the build departs from the literal entity list, and why |
| [0011](0011-project-graph-thin-front-door.md) | Project graph service is a thin front door | Registry-validated ingestion, dual-plane writes, snapshotting, project-scoped facade — nothing more |
| [0012](0012-data-profile-and-feasibility-coverage.md) | `DataProfile` entity; feasibility assessment as registry data | Closes three coverage gaps found reviewing the worked model against real delivery activities |

## Deferred, and why

**GitHub Copilot integration** — out of scope by decision. Three future
integration points: Copilot code review as a marketplace `Tool`
(`LOW_RISK_WRITE`, findings consumed as `Evidence`); GitHub Models behind the
configurable model provider; and Copilot coding agent as an `EXTERNAL_AGENT`
implementation of an `EngineeringRole`. The third needs an `EXTERNAL_AGENT`
execution model and a provider binding on `Agent` — a known, accepted refactor
of `entities/organization/agents.py` when the runtime lands.

**Document assimilation** (§17–18) — the extraction pipeline that would populate
a delivery model from Markdown, PDF and DOCX. The metamodel is ready for it:
`source_document`, `source_section` and `extraction_method` exist, and ADR-0009
guarantees extracted rules start advisory.

## Writing a new ADR

Number sequentially and keep the shape: **Context** (the forces, not the
solution) → **Decision** (stated plainly) → **Consequences** (good, costs, risks
accepted) → **Alternatives rejected** (with reasons). An ADR with an empty
alternatives section usually means the decision was not really made.
