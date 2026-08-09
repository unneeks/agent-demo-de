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
| [0013](0013-agent-based-extraction.md) | Agent-based extraction behind an `ExtractionClient` Protocol, uniform across every source kind | No per-source-type parser; two real backends (Anthropic, GitHub Copilot CLI) prove the Protocol earns its keep |
| [0014](0014-marketplace-catalog-and-role-level-composition.md) | Marketplace catalog + role-level composition, reusing existing role-satisfaction logic | `EngineeringRole.is_satisfied_by()` finally has real data; the three deferred Copilot integration points land as registry/schema facts |
| [0015](0015-evaluation-harness.md) | Evaluation harness: run a suite, gate the agent lifecycle, reusing existing scoring primitives | Closes the real dangling `gate.architecture-review` evaluation reference; `GateState.passed_evaluations` finally has an assembler |

## Deferred, and why

**GitHub Copilot integration** — the three future integration points named
below (Copilot code review as a marketplace `Tool`; GitHub Models behind the
configurable model provider; Copilot coding agent as an `EXTERNAL_AGENT`
implementation of an `EngineeringRole`) are now **delivered as registry/schema
data** (Phase 4, ADR-0014, `docs/marketplace.md`): a `Tool` action framing
Copilot review findings as `Evidence`, a worked agent proving
`model_provider="github-models"` already loads, and `ExecutionModel.
EXTERNAL_AGENT` + `Agent.external_provider` as the concrete provider binding
ADR-0009 flagged. Phase 3 (ADR-0013) had already added a narrower, fourth
integration point ahead of these three — `CopilotCliExtractionClient`, one of
two backends behind `ExtractionClient`, using the CLI for structured file
extraction, not agentic coding. **Still not started, across all four:** any
actual Copilot API/CLI/coding-agent call from a live agent runtime — that
runtime does not exist yet, and none of this phase's work executes anything.

**Agent Runtime and Project Orchestrator** — the two layers `docs/
architecture.md`'s layered diagram still marks `(later)` above `engines/
composition`/`engines/evaluation`. Phase 5 (ADR-0015) gives the evaluation
vocabulary a harness that scores caller-supplied observed values and gates
`Agent` lifecycle transitions, but nothing in the codebase yet actually
invokes an LLM, executes an agent's declared skills, or ties discovery +
composition + evaluation + impact analysis into one continuous loop for a
real project. Both remain fully unstarted.

**Document assimilation** (§17–18) — the extraction pipeline that would populate
a delivery model from Markdown, PDF and DOCX. Phase 3 (ADR-0013,
`docs/discovery.md`) delivers the code-discovery half and the Markdown slice of
this — `DeliveryArtifact` extraction and `DESCRIBES` edges to technical
entities, uniformly through the same agent-based `ExtractionClient` this note
originally anticipated. PDF and DOCX remain not started: the metamodel is
ready for them (`source_document`, `source_section` and `extraction_method`
already exist, and ADR-0009 guarantees extracted rules start advisory), but no
adapter reads either format yet.

## Writing a new ADR

Number sequentially and keep the shape: **Context** (the forces, not the
solution) → **Decision** (stated plainly) → **Consequences** (good, costs, risks
accepted) → **Alternatives rejected** (with reasons). An ADR with an empty
alternatives section usually means the decision was not really made.
