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
| [0016](0016-project-orchestrator.md) | Project orchestrator: composes discovery, impact, composition and evaluation over one project, closes their deferred write path | `IMPLEMENTED_BY`/`Evaluation`+`EVALUATES` are finally persisted; `GateState.traceability` finally has an assembler too |
| [0017](0017-agent-runtime.md) | Agent runtime: a real multi-turn planner-executor loop, all tool execution simulated | `engines/context/assembler.assemble()` finally has a caller; `ToolAction.minimum_approval` finally gates a call; the last named gap short of API/UI |
| [0018](0018-web-ui.md) | Web UI: a server-rendered, read-only dashboard, in-process, no API Gateway | Every `ProjectGraphService` method and the full marketplace/delivery-model catalog now has a human-visible viewer; API Gateway is the last layer still `(later)` |
| [0019](0019-api-gateway.md) | API Gateway: read-write `/api/*` routes, same process as the Web UI | Every write path `orchestrator`/`agent_runtime` left as a plain function call now has an HTTP caller; every layer in `docs/architecture.md`'s diagram is now built |
| [0020](0020-composition-conformance.md) | Composition calls `DeliveryContract.conformance_of()` for real, via an optional `contract` parameter on `resolve_role()` | Closes a real, self-acknowledged gap between `contracts.py`'s stated purpose and what Phase 4 actually wired up; a role-satisfying but non-conformant agent is now correctly rejected from real project staffing |
| [0021](0021-capability-gap-analysis.md) | Capability gap analysis with coarse automatic maturity inference, wired into `run_cycle()` as a new optional step | Closes the other half of the Composition Engine's original spec line; `capabilities.yaml`/`delivery_capabilities.yaml`'s `detection_hints`/`realized_by_roles` finally have a consumer |
| [0022](0022-marketplace-foundry.md) | Marketplace Foundry: mine → discover patterns → LLM-synthesize candidates → score completeness, on its own branch/PR | `discovery/extraction/`'s `ExtractionClient` Protocol gets a second real caller; a new, deliberately smaller `CandidateStatus` proves `AgentLifecycle` was the wrong lifecycle to reuse |

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

**Agent Runtime** — the one layer `docs/architecture.md`'s layered diagram
marked `(later)` through Phase 6. Phase 7 (ADR-0017, `docs/agent-runtime.md`)
delivers a real multi-turn planner-executor loop (`agent_runtime.run_agent()`)
behind two live LLM backends (Anthropic, Copilot CLI) plus a hermetic replay
backend, composed into `run_cycle()` as a new opt-in RUN AGENT step. **Still
not started:** any real tool side effect — every one of the 7 catalog tools'
actions is answered by `SimulatedToolExecutor`'s canned data, always — and
any live human-in-the-loop approval mechanism; `AutomationLevelApprovalPolicy`
is a synchronous, caller-declared, simulated authorization check, not a real
gate a human sits in front of.

**API Gateway** — delivered in Phase 9 (ADR-0019, `docs/api-gateway.md`),
the last layer `docs/architecture.md`'s layered diagram marked `(later)`.
Read-write `/api/*` routes, mounted in the same `FastAPI` app `webui/`
already builds, sharing one `ProjectGraphService`/registry — register a
project, ingest entities/relationships, trigger evaluations/gate
assessments/agent runs/full cycles, all translating JSON-safe request
fields into the same live Python objects `orchestrator`/`agent_runtime`
already require, server-side only. **Still not started:** any
authentication or authorization — every write endpoint is reachable by
anyone who can reach the process; OBSERVE/discovery over HTTP — no
endpoint accepts a filesystem path from a remote caller; rate limiting;
run-history persistence.

**Composition — capability-gap-driven role resolution** (§ per the
original spec's Composition Engine line) — ADR-0020 wired the
`conformance_of()` half of that line for real; ADR-0021
(`docs/gap-analysis.md`) delivers the other half — `engines/gap_analysis/`
infers coarse `Capability`/`DeliveryCapability` maturity from real project
facts, diffs it against a caller-supplied desired maturity, and persists
itemized `CapabilityGap`s plus advisory role recommendations, wired into
`run_cycle()` as a new optional step. Both halves of the original spec
line are now delivered.

**Marketplace Foundry** — delivered in Phase 10 (ADR-0022,
`docs/marketplace-foundry.md`), on its own branch/PR rather than an
addition to this sequential platform line. Deterministic mining and
pattern discovery over a project's already-ingested graph
(`engines/foundry/`), LLM-backed candidate content synthesis reusing
`discovery/extraction/`'s `ExtractionClient` Protocol unmodified
(`foundry/synthesis/`), and structural-completeness evaluation through the
real, unmodified evaluation harness — independently invocable via
`scripts/run_foundry.py`, never wired into `orchestrator.cycle.run_cycle()`.
**Still not started:** shadow mode; any certification workflow beyond the
4-state `CandidateStatus`; an actual publish-to-YAML mechanism (a human
hand-writes the registry diff from a certified candidate's payload today);
any new UI or API surface; cross-project/enterprise clustering;
knowledge-pack/delivery-blueprint synthesis; a continuous-learning
feedback loop from real usage; and any raw repo/document re-scanning —
Foundry mines only what `discovery/` already ingested, never duplicating
its job.

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
