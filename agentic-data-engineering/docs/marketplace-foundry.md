# Marketplace Foundry

Marketplace Foundry mines a project's already-ingested graph for recurring
engineering patterns, synthesizes candidate Skills/Tools/Agents from them,
and scores each candidate's structural completeness — a backend pipeline
through candidate synthesis and evaluation, per the user's own scoping
answer. It develops on its own branch/PR
(`claude/marketplace-foundry`) as a new, independently-shippable feature,
not an addition to the sequential phase-by-phase platform branch, though
it is numbered Phase 10 for documentation/ADR continuity. See
[ADR-0022](adr/0022-marketplace-foundry.md) for the full reasoning and the
alternatives rejected.

## The one idea that must not be compromised

**Mining and pattern discovery are pure, deterministic transformations
over already-ingested project-graph data — no LLM. Candidate *synthesis*
is the one step that calls an LLM, and it does so through the exact same
`ExtractionClient` Protocol `discovery/extraction/` already established**
(`discovery/extraction/client.py`, ADR-0013): one interface (`prompt` +
`response_schema` in, a raw `dict` out), the same two live backends reused
unmodified (`AnthropicExtractionClient`, `CopilotCliExtractionClient` —
both fully generic, neither has any file- or discovery-specific logic),
and the same two-layer defense before a response becomes a candidate
entity: `jsonschema.validate` against the exact schema the client was
asked to conform to, then Pydantic construction of the real `Skill`/
`Tool`/`Agent`, enforcing every metamodel invariant regardless of what the
LLM actually returned. **The platform, never the LLM, assigns candidate
identity** (`skill_key`/`tool_key`/`agent_key`, derived deterministically
from the pattern that produced it) **and provenance** (`INFERRED`,
confidence tied to the pattern's own `similarity_score`) — the LLM authors
descriptive/behavioral *content* only.

## Worked example

Three pipelines share a shape — `pipeline_kind="dbt_model"`,
`orchestrator="airflow"`, reading `raw_orders` and writing `stg_orders`:

```
mine_observations()  -> 3 EngineeringObservations (one per pipeline, OBSERVED)
discover_patterns()  -> 1 EngineeringPattern
                         pattern_key = pattern.pipeline_shape.dbt_model.airflow
                         frequency=3, similarity_score=1.0 (identical inputs/outputs)
foundry/synthesis/    -> one LLM call per requested candidate kind, e.g.:
                         CandidateSkill(review.proposed_key="skill.pattern.pipeline_shape.dbt_model.airflow",
                                        proposed_skill=Skill(name="Staging Orders Transform", ...))
score_candidate_completeness() -> {"candidate-io-contract-completeness": 1.0,
                                    "candidate-checklist-traceability": 0.0,
                                    "candidate-pattern-support": 0.6}
run_suite("foundry-candidate-skill-completeness", ...) -> Evaluation(passed=True)
advance_candidate(candidate, EVALUATED, evaluation=...) -> CandidateReview.candidate_status = EVALUATED
```

Every entity and edge above is written through
`ProjectGraphService.ingest_entity`/`ingest_relationship` — `foundry/run.py`
never touches `persistence.ports` directly, the same discipline
`discovery/orchestrate.py` and `orchestrator/cycle.py` already enforce.

## Mining: what's in scope, and what deliberately isn't

Foundry mines only `Pipeline`, `Test`, `DeliveryTask` and
`DeliveryActivity` entities already reachable from a project's graph node
via `ProjectGraphService` (`foundry/project_facts.py`). It never re-scans
a filesystem or re-parses a document — that is `discovery/`'s job,
already built; Foundry consumes discovery's *output*, never duplicates
its input path. `AgentRunReport`/`CycleReport` (transient, never
persisted), persisted `Evaluation` history, and `IMPLEMENTED_BY` staffing
edges are all explicitly excluded from mining this phase — real data, but
a different concern (agent-performance feedback, out of scope per the
user's own scoping answer).

## Pattern discovery: crude by design, not semantic

`engines/foundry/discovery.py` groups observations by an exact-match key
— `(source_type, activity, technology)` — and scores similarity as the
average pairwise Jaccard similarity over each observation's
`set(inputs) | set(outputs)`. **This is literal field-value grouping plus
set-overlap scoring, not semantic clustering.** Two pipelines that do the
same thing under different `pipeline_kind` strings will never group —
asserted by a dedicated test
(`test_foundry_discovery.py::TestNoSemanticClustering`), not hidden.

## Synthesis: the one LLM call, and what it is and isn't trusted with

`foundry/synthesis/schema.py::candidate_content_schema_for()` builds the
JSON Schema an LLM must conform to, starting from
`discovery.extraction.prompts.content_schema_for()` (reused directly for
stripping base `ProvenancedEntity` fields and every `EntityRef`-shaped
field), then:

- **Adds back `name`/`description`** as required, LLM-authored fields —
  discovery strips these because it auto-derives identity; Foundry
  deliberately wants the LLM's human-readable name/description, since
  that readability is the actual value synthesis adds over a
  deterministic field-copy.
- **Drops the entity's own `<kind>_key`** — the platform assigns this
  deterministically (`f"{kind}.{pattern.pattern_key}"`), mirroring
  discovery's own `suggested_id` → platform-assigned-`id` trust boundary.
- **Drops `confidence`** — platform-assigned from the pattern's
  `similarity_score`, never the LLM's own self-report.
- **For `Agent` only, also drops `status`/`certification_status`** —
  lifecycle fields; governance of a proposal lives on
  `CandidateReview.candidate_status`, not the embedded entity's own field.

A named, accepted limitation: `role_key` is **not** dropped from the
`Agent` schema, and is not validated against the real `EngineeringRole`
catalog — the LLM proposes a role key freely. Certifying that a proposed
agent's role actually exists in the marketplace is future-phase work, not
built here.

`foundry/synthesis/replay_client.py::ReplaySynthesisClient` is the
hermetic test backend: content-addressed (the request hash itself, reusing
`discovery.extraction.replay_client.build_request_hash` directly, is the
fixture filename) — simpler than `ReplayExtractionClient`'s own scheme,
which parses a `File: ...` line out of discovery's file-extraction prompt
convention that Foundry's pattern-shaped prompts don't have.

## Evaluation: structural completeness, explicitly not historical replay

`engines/foundry/evaluation.py::score_candidate_completeness()` computes
three proxy metrics from the candidate's own declared shape and the
pattern that produced it — `candidate-io-contract-completeness` (blocking:
does the payload declare non-empty inputs/outputs, or for a `Tool`, at
least one action with a non-empty input/output schema),
`candidate-checklist-traceability` (skills only, non-blocking),
`candidate-pattern-support` (`min(1.0, pattern.frequency / 5)`,
non-blocking). This codebase has no benchmark corpus or execution sandbox
to replay a candidate against — building one is its own multi-phase
effort. Scoring stays honestly narrow rather than inventing
historical-performance numbers. The real, unmodified
`engines/evaluation/harness.py::run_suite()` does the actual scoring
against these observed values; three new registry suites
(`foundry-candidate-{skill,tool,agent}-completeness`) reference them.

## Candidate lifecycle: a new, deliberately smaller status, not `AgentLifecycle`

`Agent.status: AgentLifecycle` already has `CANDIDATE`/`EVALUATED`/
`CERTIFIED` states, gated by `engines/evaluation/lifecycle.py::advance_agent()`
— but that function is structurally bound to a *registered* Agent's
`agent_key` (`evaluation.subject_ref.id == agent.agent_key`), and
`Skill`/`Tool` have no lifecycle field at all. A pre-publish candidate has
no registry identity to bind to. `CandidateStatus`
(`CANDIDATE → EVALUATED → CERTIFIED`, or `→ REJECTED` from either of the
first two) is a structural mirror of `AgentLifecycle`/`advance_agent`, not
a fork of it — `engines/foundry/lifecycle.py::advance_candidate()` checks
`evaluation.subject_ref.id == candidate.id` instead.

## Errors

| Error | Raised by | Meaning |
|---|---|---|
| `pydantic.ValidationError` | `EngineeringPattern`/`CandidateReview`/`Candidate{Skill,Tool,Agent}` constructors | A structural invariant failed (e.g. a pattern with 1 observation, a mismatched `proposed_key`, a gated status with no `evaluation_ref`) |
| `foundry.errors.FoundryError` | `foundry/synthesis/parse_response.py` | An LLM response failed JSON Schema validation, or was schema-conformant but failed entity construction (a real, named second layer of defense) |
| `foundry.errors.FoundryError` | `foundry/synthesis/replay_client.py` | No fixture for a request hash, or a fixture's prompt/schema no longer matches what was recorded |
| `ValueError` | `engines/foundry/lifecycle.py::advance_candidate()` | A gated transition with no evaluation, a wrong-subject evaluation, a failing evaluation, or an illegal status jump |

A synthesis failure for one pattern/candidate-kind is recorded in
`FoundryCycleReport.failed` and does not abort the rest of a
`run_foundry_cycle()` run (`on_error="collect"`, the default) — matching
`discovery.orchestrate`'s own per-item-failure discipline.

## What this is not

- **No shadow mode, no certification workflow beyond the 4-state
  `CandidateStatus`.** No `SHADOW`/`CANARY`/`PRODUCTION` deployment
  stages — those describe *published* artifacts.
- **No publish-to-YAML mechanism.** `CERTIFIED` is terminal; a human
  takes a certified candidate's `proposed_skill`/`proposed_tool`/
  `proposed_agent` payload and hand-writes the registry YAML diff
  themselves. This phase does not even provide a renderer function, only
  a payload shape (the real `Skill`/`Tool`/`Agent` class, embedded
  directly) proven to need no redesign to support one.
- **No new UI, no new API endpoints.**
- **No cross-project/enterprise clustering.** `EngineeringPattern.project_ref`
  is singular, not a list.
- **No knowledge-pack/delivery-blueprint synthesis.** Skills/Tools/Agents
  only.
- **No continuous-learning feedback loop.** Persisted `Evaluation` history
  from real usage is not mined to refine future synthesis.
- **No raw repo/document re-scanning.** Foundry mines only what
  `ProjectGraphService` already has; `discovery/`'s job is untouched and
  not duplicated.
- **No historical replay.** Evaluation is structural/contract-completeness
  only.
- **Not wired into `orchestrator/cycle.py`.** Invoked independently, any
  time, via `scripts/run_foundry.py` — never a `run_cycle()` step.
- **Explicitly *not* the existing `Observation` entity**
  (`domain/metamodel/entities/shared/work.py`) — that is a runtime
  drift/correction signal with `UPDATES` edges into the twin;
  `EngineeringObservation` has no update-the-twin semantics at all. Also
  explicitly *not* `engines/composition/resolution.py::CandidateAssessment`
  — that is "how one agent measures up against one role" for an
  *already-registered* Agent, unrelated to an unpublished
  `CandidateSkill`/`CandidateTool`/`CandidateAgent`.
- **No auth/RBAC/Policy Engine/Approval Gates UI/Audit system, no UI
  component library.** None of these exist anywhere in this codebase;
  this phase adds none of them.
