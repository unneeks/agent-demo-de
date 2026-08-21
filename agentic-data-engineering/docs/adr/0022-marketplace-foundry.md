# ADR-0022: Marketplace Foundry — LLM-backed candidate synthesis, on its own branch

**Status:** Accepted · **Date:** 2026-08-10 · **Phase:** 10

## Context

The user asked for a feature that learns Skills, Tools and Agents by
mining recurring engineering patterns out of an existing project,
synthesizing candidate marketplace artifacts, and evaluating them — then
pasted a 52-section spec assuming infrastructure this codebase does not
have (auth/RBAC, a Policy Engine, an Approval Gates UI, an Audit/event-log
system, a rich UI component library, a live runtime marketplace-publish
mechanism, named "Request Orchestrator"/"Agent Composer" services, asset
versioning). That mismatch was surfaced directly before any design work.
Two confirmed `AskUserQuestion` answers scoped the phase to backend
mining, pattern discovery, LLM-backed candidate synthesis and structural
evaluation — deferring shadow mode, full certification, a publish
mechanism, new UI/API, cross-project clustering, knowledge-pack/blueprint
synthesis, and a continuous-learning loop — and scoped the publish target
to a future registry-YAML diff, not a runtime-ingested entity.

A first plan draft was paused before approval with three corrections:

1. **A different branch, as a new, independently-shippable feature** —
   not an additive commit on `claude/agentic-data-engineering-platform-4kjmgt`
   (which already tracks PR #13 for the sequential phase-by-phase build).
2. **An LLM is required to generate the actual Skill/Tool/Agent content**
   — the original draft synthesized every field deterministically from a
   pattern's grouped data, which is not a real proposal a human would
   want to review.
3. **The flow is independently invocable at any time, not folded into
   `run_cycle()`** — once a project's graph exists, Foundry can be
   triggered separately, repeatedly, to look for new marketplace
   opportunities as the project evolves.

**Three findings, verified directly against real source, that changed the
entity design:**

- `EntityType.OBSERVATION` / `Observation`
  (`domain/metamodel/entities/shared/work.py:153`) already exists — "something
  noticed at runtime that should update a twin or knowledge," a different
  concept from a mined "one instance of a recurring activity." The new
  entity is named `EngineeringObservation`, with its own `EntityType`.
- `engines/composition/resolution.py::CandidateAssessment` already exists
  — "how one agent measures up against one role," for an
  *already-registered* Agent. Unrelated to Foundry's new, unpublished
  candidates.
- `Agent.status: AgentLifecycle` already has `CANDIDATE`/`EVALUATED`/
  `CERTIFIED` states, gated by `engines/evaluation/lifecycle.py::advance_agent()`
  (verified, lines 45-86), which hardcodes
  `evaluation.subject_ref.type is EntityType.AGENT` and
  `evaluation.subject_ref.id == agent.agent_key` — structurally bound to
  a registered Agent's key. A pre-publish candidate has no such identity.

## Decision

**A new `domain/metamodel/entities/foundry/` package**
(`EngineeringObservation`, `EngineeringPattern`, `CandidateReview`,
`CandidateSkill`, `CandidateTool`, `CandidateAgent`), three new
relationship types (`OBSERVES`, `CONTRIBUTES_TO`, `SYNTHESIZES`), a pure
`engines/foundry/` package (mining, pattern discovery, structural
completeness scoring, candidate lifecycle gating — no I/O, no LLM), and a
new top-level `foundry/` orchestration package whose `synthesis/`
subpackage makes the one LLM call, reusing `discovery/extraction/`'s
`ExtractionClient` Protocol and its two live backends unmodified.
`scripts/run_foundry.py` is the concrete "invoke any time" entry point,
mirroring `scripts/run_web.py`'s standalone-script convention. Developed
on a new branch, `claude/marketplace-foundry`, branched from
`claude/agentic-data-engineering-platform-4kjmgt`'s tip (`10d34e9`), with
its own PR against `main`.

**Judgment call: `CandidateStatus`, not a reuse of `AgentLifecycle`.**
`advance_agent()` is structurally bound to a registered `Agent.agent_key`;
`Skill`/`Tool` have no lifecycle field at all. Reusing `AgentLifecycle`
would be a category error, not a missed reuse opportunity. `CandidateStatus`
(`CANDIDATE → EVALUATED → CERTIFIED`, or `→ REJECTED`) is a deliberately
smaller, structural mirror of `AgentLifecycle`/`advance_agent`, built the
same way (`engines/foundry/lifecycle.py::advance_candidate()` checks
`evaluation.subject_ref.id == candidate.id` in place of `agent.agent_key`).

**Judgment call: three candidate entities, not one polymorphic
`MarketplaceCandidate`.** `Skill`/`Tool`/`Agent` are already three
separate, differently-shaped entities in this codebase. A discriminated
union would need `payload: Skill | Tool | Agent` anyway, and buys nothing
`SYNTHESIZES`'s own `target_types: [CandidateSkill, CandidateTool,
CandidateAgent]` restriction doesn't already express more precisely to
the relationship-type registry. The embedded payload is the **real**
`Skill`/`Tool`/`Agent` class, not a parallel DTO — so a future
publish-to-YAML renderer never needs a redesign; there is only one field
list, matching `registry.py`'s `_load_skills`/`_load_tools`/`_load_agents`
almost 1:1.

**Judgment call: LLM-backed synthesis reuses `discovery/extraction/`'s
`ExtractionClient` Protocol, rather than a new bespoke LLM integration.**
`discovery/extraction/` already solved "prompt + JSON Schema in,
structured dict out, uniform across replay/Anthropic/Copilot CLI
backends" (ADR-0013). Foundry's synthesis need — turn a small amount of
structured context into a schema-conforming JSON object — is the same
shape of problem, not a different one. `AnthropicExtractionClient`/
`CopilotCliExtractionClient` are reused completely unmodified (verified
directly: neither has file- or discovery-specific logic). The one new
piece is `ReplaySynthesisClient`: `ReplayExtractionClient`'s own fixture
lookup parses a `File: ...` line out of discovery's prompt convention,
which Foundry's pattern-shaped prompts don't have, so Foundry's replay
client is content-addressed instead (the request hash itself, reusing
`build_request_hash` directly, is the fixture filename) — a strictly
simpler scheme, not a re-implementation of discovery's file-lookup logic.

**Judgment call: `candidate_content_schema_for()` adds back `name`/
`description` and drops `confidence` beyond what
`content_schema_for()` already strips.** Discovery strips `name`/
`description` because it auto-derives identity from a `suggested_id`;
Foundry deliberately wants the LLM's human-readable name/description,
since that readability is the actual value synthesis adds over the
deterministic field-copy the first plan draft proposed. `confidence` is
dropped because it is platform-assigned from the pattern's own
`similarity_score`, never the LLM's self-report — the same "never a
literal the model invents" discipline applied to one more field.

**Judgment call: evaluation stays structural/contract-completeness,
explicitly not historical replay**, unaffected by the LLM-synthesis
correction. This codebase has no benchmark corpus or execution sandbox to
replay a candidate against; inventing `observed_values` from anything but
the candidate's own declared shape would be worse than a narrow, honestly
labelled check.

**Judgment call: `foundry/project_facts.py` duplicates ~15 lines of
`webui/graph_discovery.py`'s traverse-then-fetch idiom rather than
importing it.** A backend orchestration package depending on the UI layer
inverts `docs/architecture.md`'s layered diagram. A small, named
duplication in exchange for correct dependency direction.

## Consequences

**Good.** A real, working mining → pattern-discovery → LLM-synthesis →
evaluation pipeline exists, independently invocable against any project
whose graph is already populated. The synthesized candidate payload is
the real `Skill`/`Tool`/`Agent` class, so a future publish-to-YAML
renderer needs no redesign. No second LLM-integration pattern was
introduced — `discovery/extraction/`'s `ExtractionClient` Protocol now
has two real callers, proving its "one interface, multiple real backends"
design (ADR-0007/ADR-0013) generalizes.

**Costs, stated honestly.** Pattern discovery is exact-match, not
semantic — two pipelines doing the same thing under different labels
never group. `role_key` on a candidate `Agent` is LLM-authored and
unvalidated against the real `EngineeringRole` catalog. No benchmark
corpus means evaluation cannot measure whether a synthesized skill
actually *works*, only whether it is structurally complete. This phase
ships on a separate branch/PR from the sequential platform line, which a
future merge will need to reconcile explicitly (a deliberate cost of the
user's own "new feature" framing, not an oversight).

**One found, unrelated gap, fixed narrowly.** `EvaluationSuite.level`'s
allowed set (`domain/metamodel/entities/evaluation/evaluation.py`) had no
`"tool"` — the only existing file outside brand-new Foundry modules this
phase touches. Added `"tool"` (one line), with its own test.

**One found, structural gap in the fixture-staleness design, fixed by
re-recording.** `discovery/extraction/prompts.py`'s technical-extraction
response schema embeds the *full* `EntityType` enum (as
`RelationshipCandidate.target_kind`'s allowed values). Adding the 5 new
`EntityType` members this phase needed changed that schema for every
existing discovery golden fixture, invalidating their committed
`request_hash` and failing `test_discovery_worked_example_replay.py`.
Fixed by replaying the real `discover_project` flow against the real
sibling project with a rehashing client that recomputes each fixture's
`request_hash` under the current schema while leaving `raw_response`
untouched — not a new bug in this phase's code, but a real, structural
fragility (any future `EntityType` addition will do this again) worth
naming rather than silently working around.

## Alternatives rejected

**Reusing `AgentLifecycle` for `CandidateStatus`.** Rejected —
`advance_agent()` is structurally bound to a registered `Agent.agent_key`;
`Skill`/`Tool` have no lifecycle field to reuse at all.

**One polymorphic `MarketplaceCandidate` entity.** Rejected — `Skill`/
`Tool`/`Agent` are already three shapes; a discriminator adds nothing the
relationship-type registry doesn't already validate more precisely via
three concrete target types.

**A new, bespoke LLM client abstraction for Foundry.** Rejected —
`discovery/extraction/`'s `ExtractionClient` Protocol already solves the
exact shape of problem; a second abstraction would be pure duplication.

**Historical-replay evaluation.** Rejected (unchanged from the original
plan) — no benchmark corpus or execution sandbox exists in this codebase.

**Wiring Foundry into `orchestrator/cycle.py`.** Rejected per the user's
explicit "invoked independently, any time" direction — Foundry is a
separate entry point, not a forced step in every cycle.

**Reusing `webui/graph_discovery.py` for `foundry/project_facts.py`.**
Rejected — a backend package depending on the UI layer inverts the
layered architecture; a small, named duplication was preferred.
