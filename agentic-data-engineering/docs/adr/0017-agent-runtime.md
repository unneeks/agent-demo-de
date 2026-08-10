# ADR-0017: A real multi-turn agent runtime, all tool execution simulated

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 7

## Context

`Agent Runtime` was the one layer `docs/architecture.md`'s layered diagram
still marked `(later)` through Phase 6. Every prior phase's own docs state
"no agent runtime, no LLM calls" as an explicit non-goal
(`docs/marketplace.md`, `docs/evaluation.md`, `docs/orchestrator.md`).
Phase 7 crosses that line, on explicit user direction, with three
confirmed scope constraints from two rounds of clarification:

1. **A real multi-turn planner-executor loop** — the agent plans, calls
   multiple tools (including `LOW_RISK_WRITE` ones gated by
   `ToolAction.minimum_approval`), iterates up to `max_iterations`, and
   produces a richer result. Not a minimal single-skill call.
2. **All tools simulated** — every backend for all 7 marketplace catalog
   tools is an explicit stub returning structured canned data. No real
   side effect anywhere, ever.
3. **Both Anthropic and Copilot CLI**, matching Phase 3's two-live-backend
   precedent (`AnthropicExtractionClient`/`CopilotCliExtractionClient`
   behind one `ExtractionClient` Protocol), plus a third hermetic replay
   backend for tests.

Two facts, verified directly against the real registry data before
designing anything, decided the approval-gating design:

- `metamodel-registry/risk.yaml`'s `approval_matrix` already resolves
  `LOW_RISK_WRITE` under `SUPERVISED_AUTONOMOUS` to `SAMPLED_QA`, and under
  `ASSISTED`/`AUTONOMOUS` to `NONE`, with zero registry change needed.
- `ToolAction.minimum_approval` (`domain/metamodel/entities/organization/
  agents.py`) defaults to `ApprovalLevel.NONE`, and — confirmed by direct
  read — was never set to anything else anywhere in
  `metamodel-registry/tools.yaml` before this phase: all 11 actions across
  the 7 catalog tools relied on the default. The field the user's scope
  names specifically was inert data.
- `domain/metamodel/enums.py` had `TRUST_ORDER` for `TrustLevel` but no
  equivalent ordering for `ApprovalLevel` — confirmed by grep — needed to
  combine two independently-sourced approval requirements via `max()`.

## Decision

**A new top-level package, `agent_runtime/`, with `run_agent()`** as the
multi-turn loop: build context via the first real caller of
`engines.context.assembler.assemble()`, call an `AgentLLMClient` backend
for one turn at a time, resolve and gate each requested tool call, dispatch
approved calls to a `ToolExecutor`, feed results (or synthetic denials)
back into the transcript, and repeat up to `max_iterations`.

**Why a new top-level package, not `orchestrator/agent_runtime.py`.**
Every prior phase that added a genuinely new deterministic engine got
`engines/<name>/`; every phase that added persistence/composition over
existing engines got its own top-level package (`project_graph/`,
`discovery/`, `orchestrator/`). Agent runtime is neither: it is not a pure
function (its whole job is to call an LLM, deliberately not pure), and
unlike `orchestrator/` (which "composes; it invents nothing" — ADR-0016) it
is genuinely new logic — nothing in the codebase executed a tool or called
an LLM before this phase. It earns its own top-level package for the same
reason `discovery/` did in Phase 3.

**`ToolExecutor` — one interface (ADR-0007's pattern), exactly one backend
this phase.** Unlike `ExtractionClient` (two live backends plus replay from
Phase 3 on), `ToolExecutor` ships only `SimulatedToolExecutor`, per the
user's explicit "all tools simulated" scope. Still a `Protocol`, for the
same three reasons ADR-0007 gives: self-documenting contract, a clean
swap-in point for a future real backend, and substitutable test doubles.

**`AgentLLMClient` — one turn per call, not a whole conversation.** Turn
accumulation, `max_iterations`, tool dispatch and approval gating all live
in `agent_runtime/loop.py`, never inside a backend — the direct analogue of
`ExtractionClient.extract()` never seeing `parse_response.py`'s validation.
Three backends: `AnthropicAgentClient` (extends
`AnthropicExtractionClient`'s single-forced-tool pattern to
`tool_choice="auto"` with turn accumulation moved to the loop),
`CopilotCliAgentClient` (a larger, explicitly accepted risk than the
existing single-shot Copilot CLI client — no known documentation of a
non-interactive, multi-turn, tool-calling contract for this CLI), and
`ReplayAgentClient` (a genuinely new fixture shape — see below).

**Judgment call: `ReplayAgentClient` checks staleness once, at session
start, not per turn.** `ReplayExtractionClient` hashes every individual
call's `(prompt, schema)` because each call is independent and
re-verifiable against its own source file. A multi-turn session cannot be
hashed that way: turn 3's `messages` already contains turn 2's tool result,
which came from `SimulatedToolExecutor`, not an external source — hashing
per-turn would make fixtures brittle to any wording change in an
intermediate canned tool response, for no real staleness-detection benefit.
`build_task_hash(agent_key, task, tools)` hashes only the opening state —
the inputs that are genuinely external and could drift.

**Judgment call: two independently-sourced approval requirements combine
via `max()`, and one worked-example registry edit makes `minimum_approval`
load-bearing.** `AutomationLevelApprovalPolicy.decide()` computes
`max(registry.required_approval(action_class, automation_level),
action.minimum_approval)` using a new `APPROVAL_ORDER` total order. Because
the matrix alone already produces a non-`NONE` result for `LOW_RISK_WRITE`
under `SUPERVISED_AUTONOMOUS`, and `minimum_approval` was `NONE`
everywhere, the field was previously inert. `github.
comment_on_pull_request` now carries `minimum_approval: SINGLE_REVIEWER` —
a plausible real floor (posting is visible to humans outside this platform
immediately) that holds under every automation level, including `ASSISTED`
and `AUTONOMOUS` where the matrix alone says `NONE`. "Gated" is defined
concretely and honestly: a synchronous, caller-declared, simulated
authorization check, fail-closed (`granted` defaults to `NONE`) — not a
live human-in-the-loop mechanism, because none exists in this codebase.

**Judgment call: an agent run's rich output is not auto-translated into
`EvaluationRequest.observed_values`.** `orchestrator.evaluate.
run_evaluations()`'s own docstring already draws this boundary
("observed_values is never touched or synthesized"), and `run_suite()`
itself raises on a missing required metric because scoring is
domain-specific. `AgentRunReport.evidence: list[Evidence]` is the bridge
instead — a real, ingestible artifact a caller can hand-wire into an
`EvaluationRequest`, never invented plumbing between the two.
`CycleReport.agent_runs` stands as its own reportable section.

**One small, verified-necessary metamodel addition:** `APPROVAL_ORDER` in
`domain/metamodel/enums.py`, placed next to `TRUST_ORDER`, same shape, same
purpose.

**One inherited packaging gap closed in the same edit, not new scope:**
`pyproject.toml`'s `[tool.setuptools.packages.find] include` list was
missing `orchestrator*` since Phase 6 (confirmed by direct read; tests
passed only because `pythonpath = ["."]` bypasses installed-package
resolution). Fixed alongside adding `agent_runtime*`.

**`run_cycle()` gains one new optional parameter, `agent_run_requests`,
composed after SELECT AGENTS and before EVALUATE** — never automatic,
mirroring how `evaluation_requests`/`gates` are already caller-opt-in.
`orchestrator/agent_step.py`'s `run_agents()` is the thin wrap-and-link,
mirroring `orchestrator/staffing.py`'s shape: the only new code is linking
an `AgentRunOutcome` back to the `StaffingOutcome` (if any) that named the
agent, `run_agent()` itself is untouched.

## Consequences

**Good.** The platform can now run a real multi-turn agentic loop against
its own catalog data — an agent's declared skills, knowledge packs and
tools become a real system prompt and a real tool-use definition list, not
just registry rows. `engines/context/assembler.assemble()` finally has a
real caller. `ToolAction.minimum_approval` is finally load-bearing.
`CycleReport.agent_runs` closes the last named gap in
`docs/architecture.md`'s layered diagram short of API/UI.

**Costs, stated honestly.** No tool call in this codebase ever has a real
side effect — that is exactly this phase's scope, not a shortfall, but it
means "the agent commented on the PR" is never literally true after this
phase, only "the agent would have, and was gated as if it would." The
Copilot CLI backend's multi-turn tool-calling contract is unverified and
may not exist as assumed. There is still no live human-in-the-loop
approval mechanism anywhere — `AutomationLevelApprovalPolicy` is a
simulated, caller-declared authorization, not a real gate a human sits in
front of. `WORKFLOW_DRIVEN`/`EXTERNAL_AGENT` execution models remain
entirely outside this runtime's scope.

## Alternatives rejected

**Per-turn fixture hashing for `ReplayAgentClient`**, mirroring
`ReplayExtractionClient` exactly. Rejected — mid-session turns depend on
`SimulatedToolExecutor`'s own canned output, not an external source, so a
per-turn hash would make fixtures brittle for no real staleness-detection
benefit.

**Filtering `build_tool_definitions()` to READ_ONLY actions only**, so a
dangerous call could never even be offered to the model. Rejected — the
approval gate, not tool *availability*, is the enforcement point
`docs/architecture.md`'s own governance table already frames ("High-risk
actions need a human" is enforced structurally, never by omission); hiding
capability would also make a denial's reasoning untestable, since the model
would never ask.

**Auto-translating `AgentRunReport` into `EvaluationRequest.
observed_values`** via some generic reducer over tool outputs. Rejected —
scoring is domain-specific (`run_suite()`'s own precondition), and Phase 6
already refused to add generic reduction logic for a structurally similar
case (`evaluate_checklist()`'s `ChecklistItemResult` input, deliberately
left caller-supplied to hold a crisp scope line).

**Silently leaving `ToolAction.minimum_approval` at `NONE` everywhere**,
since the matrix alone already produces a plausible result under
`SUPERVISED_AUTONOMOUS`. Rejected — the user's scope names
`minimum_approval` specifically, and shipping it provably inert would
misrepresent the phase's own stated scope as delivered when it wasn't.

**Making `agent_run_requests` automatic for every staffed agent** (i.e.
running whatever `select_agents()` resolves without a separate caller
opt-in). Rejected — staffing produces catalog-level candidates; running one
is a separate, deliberate, potentially-costly act, the same reasoning
`evaluation_requests`/`gates` already apply.
