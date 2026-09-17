# Agent Runtime

Every other layer `docs/architecture.md`'s layered diagram names is real
code: metamodel, project graph service, discovery, marketplace/composition,
evaluation harness, project orchestrator. `Agent Runtime` was the one layer
still marked `(later)` through Phase 6 — the point at which the platform
first actually invokes an LLM to run an agent's declared skills against
real tools, inside the orchestrator's loop. Every prior phase's own docs say
so plainly: `docs/marketplace.md`, `docs/evaluation.md` and
`docs/orchestrator.md` each state "no agent runtime, no LLM calls" as an
explicit non-goal. Phase 7 is the phase that crosses that line. See
[ADR-0017](adr/0017-agent-runtime.md) for the full reasoning and the
alternatives rejected.

## The one idea that must not be compromised

**`run_agent()` calls real backends behind real Protocols; it invents no
scoring and executes no real side effect.** Every tool call is answered by
`SimulatedToolExecutor`'s canned data, always — regardless of which
`AgentLLMClient` backend drives the loop. The Protocol boundary
(`AgentLLMClient`, `ToolExecutor`) is what makes "simulated today, real
tomorrow" a backend swap, not a rewrite — the exact discipline
`discovery.extraction.ExtractionClient` already proved out in Phase 3
(ADR-0007's "one interface, multiple real backends" pattern).

## The composed pipeline

```
run_agent(agent, registry, task, llm_client, tool_executor,
          context_policy, approval_policy, max_iterations)

  build_agent_context()    assemble() over the agent's declared skills   engines/context,
                            and knowledge_packs -- the first real caller  Phase 1, unused
                            of assemble() through Phase 6                until now
        |
        v
  render_system_prompt()   bundle -> the text a model actually sees      new
        |
        v
  loop up to max_iterations:
    llm_client.next_turn()     one turn: text and/or tool_use requests   new
        |
        v
    for each requested tool call:
      resolve (Tool, ToolAction) from the real catalog
      approval_policy.decide()      matrix-derived x minimum_approval    new
      if approved: tool_executor.execute()   -- always SimulatedToolExecutor
      else: a synthetic denial fed back as the tool result
        |
        v
    stop when stop_reason != "tool_use", or max_iterations is reached

  -> AgentRunReport(turns, tool_calls, evidence, completed, stop_reason)
```

`orchestrator/agent_step.py`'s `run_agents()` wraps this as `run_cycle()`'s
new, optional RUN AGENT step, placed after SELECT AGENTS and before
EVALUATE — never automatic. Staffing produces catalog-level candidates
(Phase 6); running one is a separate, deliberate, potentially-costly act, so
`agent_run_requests` is caller-opt-in exactly as `evaluation_requests`/
`gates` already are.

## `ToolExecutor`: one interface, exactly one backend this phase

Mirrors `ExtractionClient`'s Protocol shape (ADR-0007) — one call in (a
tool, an action, an input dict), one dict out. Unlike `ExtractionClient`,
which shipped two live backends plus a replay backend from Phase 3 on,
`ToolExecutor` ships **one** concrete implementation this phase,
`SimulatedToolExecutor`, and no live backend at all. This is the user's own
scope for this phase, stated plainly rather than glossed over: every real
catalog action (all 7 tools, 11 actions in
`metamodel-registry/tools.yaml`) has a fixed, deterministic canned response
— READ_ONLY actions return query-shaped data, LOW_RISK_WRITE actions return
only an id/url-shaped acknowledgment, and `SimulatedToolExecutor` holds no
mutable state, so nothing it returns can look like it mutated shared state,
because nothing ever does. The Protocol still earns its keep for the same
three reasons ADR-0007 gives: the contract is self-documenting, a future
phase adding a real backend is exactly the swap-in the pattern exists for,
and tests can substitute an alternate stub (one that raises, one with
overrides) without subclassing anything.

## `AgentLLMClient`: extending the single-forced-tool pattern to multi-turn

`discovery.extraction.anthropic_client.AnthropicExtractionClient` calls the
Messages API once, with a single forced tool, to get one schema-shaped
object back. `agent_runtime.anthropic_client.AnthropicAgentClient` is its
multi-turn sibling: `tool_choice={"type": "auto"}` instead of a forced
tool, and a Protocol that returns **one turn** rather than a whole
conversation — turn accumulation, `max_iterations`, tool dispatch and
approval gating all live in `agent_runtime/loop.py`, never inside a
backend, so no backend duplicates that logic.

Three backends, matching Phase 3's two-live-plus-replay precedent exactly:

- **`AnthropicAgentClient`** — same lazy-import-of-`anthropic` and
  `ANTHROPIC_API_KEY`-or-explicit-key constructor pattern as the extraction
  client, and the same implementation-time risk carried forward
  unmodified: the exact `tool_choice`/`stop_reason`/content-block shapes
  assumed here could not be verified against live documentation from the
  environment this was written in. Treat every constant as a best-effort
  placeholder until checked against real SDK docs.
- **`CopilotCliAgentClient`** — a larger, differently-shaped risk than the
  Anthropic backend's, and larger still than the existing single-shot
  Copilot CLI extraction client's: it needs the CLI to accept a rendered
  tool catalog and the full transcript-so-far on every turn and hand back
  one turn's structured intent as JSON. There is no known documentation of
  a non-interactive, multi-turn, tool-calling contract for this CLI —
  stated as a known, accepted, larger risk in ADR-0017, not silently
  designed around. If the real CLI cannot be driven this way, this backend
  fails the same safe way a malformed Anthropic response does: an
  `AgentRuntimeError`, never a partially-trusted guess.
- **`ReplayAgentClient`** — hermetic, fast, no network or credentials. A
  genuinely new fixture shape, not a copy of `ReplayExtractionClient`'s
  per-call request hash — see "Session-start-only staleness" below.

## Session-start-only staleness, not per-turn

`ReplayExtractionClient` hashes every individual call's `(prompt, schema)`
because each call is independent and re-verifiable against its own source
file. A multi-turn session cannot be hashed that way: turn 3's `messages`
already contains turn 2's tool result, which came from
`SimulatedToolExecutor`, not from an external source. Hashing per-turn
would make every fixture brittle to any wording change in an intermediate
canned tool response, for no real staleness-detection benefit — there is
nothing external a mid-session turn could go stale against the way a
source file can go stale.

So `ReplayAgentClient` checks staleness **once, at session start**, over
`(agent_key, task, tool catalog)` — the only inputs that are genuinely
external and could drift:

```python
def build_task_hash(agent_key: str, task: str, tools: list[ToolDefinition]) -> str: ...
```

Fixtures live at
`tests/fixtures/agent_runtime/golden/<agent_key>__<slug(task)>.json`,
mirroring `slug_for_path`'s `/` → `__` convention. Exhausting a session's
recorded turns raises `FixtureExhaustedError` — the loop never repeats the
last turn to paper over a script that ran out.

## Gating `ToolAction.minimum_approval`, concretely

Before this phase, `ApprovalLevel`/`ActionClass`/`AutomationLevel`/
`registry.approval_matrix`/`registry.required_approval()` were 100%
descriptive data — nothing enforced them live, and there is no
pending-approval or pause-resume concept anywhere in this codebase.
`AutomationLevelApprovalPolicy` is what "gated" concretely means here: a
synchronous, caller-declared, simulated authorization check, computed
before dispatch and refused — never silently downgraded — if the caller's
declared grant falls short.

Two independently-sourced requirements combine via `max()`:

```python
required = max(
    registry.required_approval(action.action_class, automation_level),  # the matrix
    action.minimum_approval,                                            # the action's own floor
    key=lambda level: APPROVAL_ORDER[level],
)
approved = APPROVAL_ORDER[granted] >= APPROVAL_ORDER[required]
```

`APPROVAL_ORDER` (`domain/metamodel/enums.py`, next to `TRUST_ORDER`) is a
new total order over `ApprovalLevel` — verified necessary by grep: no such
ordering existed before this phase.

**The worked example that makes `minimum_approval` load-bearing.** Before
this phase, `metamodel-registry/tools.yaml` set `minimum_approval` on
nothing — all 11 actions across the 7 catalog tools relied on the
`ApprovalLevel.NONE` default, and `registry.approval_matrix`'s own data
already resolves every `LOW_RISK_WRITE` action to `SAMPLED_QA` under
`SUPERVISED_AUTONOMOUS` with zero registry change. That means the field the
user's scope names specifically was inert: it never changed an outcome the
matrix didn't already produce. `github.comment_on_pull_request` now
carries `minimum_approval: SINGLE_REVIEWER` — a plausible real floor (a
posted comment is visible to humans outside this platform immediately, so
it should never go out unreviewed, not even under `ASSISTED` mode, where
the matrix alone says `NONE`):

```
ASSISTED, comment_on_pull_request:
  matrix alone:            LOW_RISK_WRITE -> NONE
  matrix + minimum_approval:                max(NONE, SINGLE_REVIEWER) -> SINGLE_REVIEWER
```

Denied by construction unless the caller explicitly grants `SINGLE_REVIEWER`
or higher — fail-closed, matching `Agent.human_approval_required: bool =
True`'s own default posture. A denied call is never a silent no-op: the
loop records a `ToolCallRecord(executed=False, error=...)` and feeds a
synthetic denial back into the transcript as the tool's result, so the
model can genuinely react — try something else, or stop.

## Wiring `engines/context/assembler.assemble()`

`assemble()` has been pure, deterministic and LLM-free since Phase 1, with
zero callers outside its own test suite through Phase 6. `agent_runtime/
context.py`'s `build_agent_context()` is the first real caller:
`ContextItem`s built from an agent's declared `knowledge_packs` and
`skills`, both mapped to `ContextItemKind.KNOWLEDGE` — an honest fit for
"what the agent needs to know to act," not a metamodel gap.
`render_system_prompt()` supplies the one step `assemble()` deliberately
stops short of: turning a `ContextBundle` into the text a model actually
sees.

## Evidence, and why an agent run does not feed `observed_values` automatically

`orchestrator.evaluate.run_evaluations()`'s own docstring already draws
this boundary: *"`observed_values` is never touched or synthesized here —
plain caller input straight through to `run_suite()`."* `run_suite()`
itself raises on a missing required metric because scoring is
domain-specific — what counts as "impacted-asset-coverage" from a pytest
run varies by suite, and inventing a generic reducer here would be exactly
the kind of new scoring logic Phase 6 already refused to add.

So an `AgentRunReport`'s rich output is **not** auto-translated into an
`EvaluationRequest`. Instead, `run_agent()` produces
`AgentRunReport.evidence: list[Evidence]` — one per evidence-worthy tool
call (`pytest.run_tests` → `test_result`, `github.copilot_code_review` →
`review_record`, everything else that executed → `tool_output`) — a real,
ingestible artifact a caller can hand-wire into
`EvaluationRequest(evidence_refs=..., observed_values=<caller-computed>)`
and feed into the same `evaluation_requests` list `run_cycle()` already
accepts. `CycleReport.agent_runs` stands as its own reportable section,
exactly as `staffing`/`evaluations`/`gate_readiness` already are separate
rather than folded together.

## Worked example

```python
report = run_agent(
    registry.agents["regression-agent"], registry,
    "Run the regression suite for PR-482",
    llm_client=AnthropicAgentClient(),            # or ReplayAgentClient / CopilotCliAgentClient
    tool_executor=SimulatedToolExecutor(),
    context_policy=my_policy,
    approval_policy=AutomationLevelApprovalPolicy(
        automation_level=AutomationLevel.SUPERVISED_AUTONOMOUS,
        granted=ApprovalLevel.SAMPLED_QA,
    ),
)
# report.turns:      the full transcript, turn by turn
# report.tool_calls: pytest.run_tests -- executed, approval.required=SAMPLED_QA
# report.evidence:   one Evidence(evidence_kind="test_result", ...)
# report.completed:  True, stop_reason "end_turn"
```

Composed into a cycle:

```python
run_cycle(
    service, registry, delivery_model, project_ref, metadata,
    agent_run_requests=[
        AgentRunRequest(
            agent_key="regression-agent", task="...",
            llm_client=..., tool_executor=SimulatedToolExecutor(),
            context_policy=..., approval_policy=...,
            staffing_outcome=staffing_outcome,   # links back to SELECT AGENTS, optional
        ),
    ],
)
# report.agent_runs: [AgentRunOutcome(agent_key="regression-agent", ...)]
```

## Errors

| Error | Raised when |
|---|---|
| `AgentRuntimeError` | A live backend can't be constructed (no API key / no binary on PATH) or a live call fails structurally |
| `UnknownToolActionError` | A model calls a `(tool_key, action_name)` pair not in the catalog, or `SimulatedToolExecutor` has no canned response for a known pair -- recorded on the `ToolCallRecord`, never fatal to the loop |
| `FixtureExhaustedError` | `ReplayAgentClient` is asked for a turn beyond what a session fixture recorded |
| `IngestionError`/`KeyError` (orchestrator) | Recorded as a `CycleFailure` under `on_error="collect"` (default); re-raised immediately under `"fail_fast"` |

## What this is not

- **No real tool side effects, ever.** `SimulatedToolExecutor` is the only
  `ToolExecutor` this phase ships; no live `git`/`github`/`pytest`/`neo4j`/
  `bigquery`/modeling-tool/metadata-platform call exists anywhere in this
  repo after Phase 7.
- **No live human-in-the-loop approval workflow.**
  `AutomationLevelApprovalPolicy` is a synchronous, caller-declared,
  simulated authorization check — there is no pending-approval state, no
  pause/resume, no notification to an actual human, and none of that is
  silently implied by the word "gated."
- **No autonomous production writes.** Everything `SimulatedToolExecutor`
  returns is canned; nothing this phase produces reaches a real system of
  record.
- **No scheduled/daemon execution.** `run_agent()` is one call, over one
  agent, for one task, triggered by a caller — the same posture
  `run_cycle()` already states for itself.
- **No multi-agent coordination.** `AgentRunRequest`/`run_agents()` run
  agents independently, one `AgentRunReport` per request; no agent's
  transcript or tool result is shared with another agent's run in this
  phase.
- **No `WORKFLOW_DRIVEN` or `EXTERNAL_AGENT` execution.** `run_agent()`
  implements the `SINGLE_SHOT`/`ITERATIVE`/`PLANNER_EXECUTOR` family as one
  parameterized loop; `EXTERNAL_AGENT` structurally cannot be run by this
  platform's own runtime (`Agent._external_agent_needs_a_provider` already
  says so), and `WORKFLOW_DRIVEN` has no declared workflow-definition
  entity in the metamodel yet to execute against.
- **No automatic translation of an agent run into
  `EvaluationRequest.observed_values`.** Stays caller-computed, exactly as
  `run_suite()` already requires.
- **No API, no UI.** Only these two layers now remain marked `(later)` in
  `docs/architecture.md`'s diagram after this phase.
