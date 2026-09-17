# ADR-0023: AgentCore Harness backend + live multi-agent workflow dashboard

**Status:** Accepted · **Date:** 2026-09-17 · **Phase:** —

## Context

This platform's agent runtime (ADR-0017) ships three `AgentLLMClient`
backends (Anthropic, Copilot CLI, replay) but no path to a model hosted in
a customer's own AWS account, and no UI that shows several agents
progressing through a delivery model's real phases at once -- `webui/`'s
existing six routes are read-only, backward-looking views over a project
already ingested, not a live view of work in progress
(`docs/web-ui.md`: "no cycle/agent-run history").

**Scope, per explicit user direction:** build the AgentCore integration
first; GitHub Copilot coding agent dispatch (the other integration the
request named) is deferred to a later pass and is untouched here --
`Agent.execution_model == EXTERNAL_AGENT`/`external_provider ==
"github-copilot-coding-agent"` stays exactly as registered since ADR-0014,
unexecuted.

**Verified directly before designing anything**, rather than assumed:
installed the real `boto3`/`botocore` packages in a scratch venv and read
`botocore/data/bedrock-agentcore/2024-02-28/service-2.json` (not scraped
docs -- several AWS documentation domains were unreachable from this
environment's network policy). Two operations exist:
`InvokeAgentRuntime` (a raw blob in, blob out -- the caller and the
hosted code must agree on their own envelope) and **`InvokeHarness`**
(structured `messages`/`tools`/`model`, Anthropic/Bedrock-Converse-style
content blocks). `InvokeHarness`'s `HarnessInlineFunctionConfig` tool type
is documented verbatim as *"When the agent calls this tool, the tool call
is returned to the caller for external execution"* -- exactly the
client-side tool bridge the request described, already built into the
service, not something to invent a custom JSON envelope for. The user's
own phrase, "agents deployed in AgentCore as harness," names this
operation specifically, confirmed against the real API rather than
assumed from the phrase alone.

Also verified: `agent_runtime.llm.AgentLLMClient`'s existing contract
(`next_turn(*, system_prompt, messages, tools) -> AgentTurnResult`, one
turn at a time) and `agent_runtime.loop.run_agent()`'s existing dispatch
loop (call → resolve tool calls → execute → append `tool_result` → call
again) together already implement "the harness returns a typed message
indicating a tool call, the orchestrator calls the local function, then
resumes the harness" end to end. A new backend only has to translate
between this platform's Anthropic-dialect transcript and AgentCore's
content-block dialect; no new orchestration primitive was needed.

## Decision

**`agent_runtime/agentcore_client.py`: `AgentCoreHarnessClient`, a fourth
`AgentLLMClient`.** Calls `boto3.client("bedrock-agentcore").
invoke_harness(...)`, advertising every catalog tool as
`HarnessTool{type:"inlineFunction"}`. Auth is the ambient boto3 default
credential chain only -- no explicit AWS keys are ever constructed or
accepted anywhere in this code, satisfying "the web app should use the
AWS-logged-in user's credentials" by construction rather than by building
a credential-passing mechanism. `runtimeSessionId` is generated once per
client instance and reused across every `next_turn()` call on it (the
"resume from where it stopped" the request asked for); real token usage
and latency are read from `HarnessMetadataEvent` -- this **is** "the
appropriate AgentCore API for the metrics in the picture," not a separate
lookup.

**A small, additive fix was needed to carry that telemetry anywhere:**
`AgentTurnResult.raw` was already being computed by every backend and
silently discarded by `run_agent()` before this ADR -- `AgentTurn` gained
a `raw: dict` field (default `{}`, every existing caller unaffected) so
real backend-reported usage/latency reaches a caller at all.

**`agent_runtime/local_tool_executor.py`: `LocalToolExecutor`, the first
real (non-simulated) `ToolExecutor`** -- runs on the same machine as the
web app, which is "the developer machine" a local AgentCore tool call is
returned to. Deliberately partial: only `git`/`pytest`
(subprocess)/`github` read+comment (the `gh` CLI, the same binary
`discovery/extraction/copilot_cli_client.py` already standardizes on)
have a generic developer-machine realization; everything else
(`neo4j.traverse`, `bigquery.profile_query`, `modeling-tool.*`,
`metadata-platform.*`, `github.copilot_code_review`) delegates to a
caller-supplied `fallback` executor or raises -- never a fabricated
response for a call nobody implemented for real.

**`orchestrator/workflow.py`: `WorkflowRunner`, the new stateful
orchestrator** the dashboard polls. Unlike `run_cycle()` (one call, one
final report), a workflow run is watched across many HTTP requests, so it
keeps live state (one thread per agent slot, a lock-guarded snapshot) in
`webui`'s `app.state.workflow_runs` -- in-memory only, gone on a server
restart, stated plainly rather than implied otherwise. Live mode drives
the **existing, unmodified** `run_agent()` once per work product; demo
mode is a scripted state machine over the same status states, driven by
`metamodel-registry/workflow_templates.yaml`'s own declared
`demo_duration_seconds`/`demo_tokens` -- a deliberate simplification from
the plan this was built against, which had proposed hand-authoring
`ReplayAgentClient` fixtures for every one of 28 work products across 4
agents. That would have proven the replay backend scales to a whole
workflow, which demo mode doesn't need to prove -- demo mode exists so
the dashboard can be shown with zero credentials, and a scripted state
machine does that directly.

**`webui/`: `/workflows` (HTML) + `/api/workflows` (JSON).** Starting a
run returns immediately with a run id; the dashboard polls
`GET /api/workflows/{run_id}` every few seconds via a small vanilla-JS
script (no framework, matching this codebase's existing plain-CSS
convention). A denied tool call pauses that agent slot and surfaces in
the snapshot's `human_attention` list with the real denial reason;
`POST .../approve` retries the same work product with an elevated
`ApprovalLevel` -- a fresh `run_agent()` call, not a mid-turn resume,
since nothing in this runtime supports pausing a live model call across
HTTP requests.

**Two real, narrowly-scoped environment fixes, found while building
this, not before it:** `python-multipart` was missing from the `web`
extra (Starlette's `request.form()`, needed for the HTML start form,
requires it); and a pre-existing `anyio`/`starlette` version pairing in
this environment turned every `fastapi.testclient` import into a
collection error under this repo's strict `error::DeprecationWarning`
filter (confirmed pre-existing via `git stash`, unrelated to this
change) -- fixed with one narrow ignore-by-message filter, which also
unblocked the pre-existing webui/API test files in this environment.

## Consequences

**Good.** A real AWS AgentCore Harness can now drive this platform's
agent loop with zero code changes to `agent_runtime/loop.py` -- the
Protocol boundary ADR-0017 established paid for itself exactly as
intended. The dashboard gives the platform a live, itemized view of
multi-agent progress that `docs/web-ui.md` had explicitly named as
missing.

**Costs, stated honestly.** `AgentCoreHarnessClient` is built against the
documented `service-2.json` shape, not live-verified against a real AWS
account or a real deployed Harness -- no AWS credentials exist in the
environment this was written in. Covered by unit tests against a
stubbed `boto3` client (request/response shape, session continuity, error
mapping), not an end-to-end call. `LocalToolExecutor` covers 4 of 11
catalog actions for real; the rest need a caller-supplied fallback.
Workflow runs are in-memory only -- a server restart loses every run's
progress, and nothing here persists a `WorkflowSnapshot` as a durable
graph fact.

**Risk accepted.** A gap recommendation/work-product's `resolve_role()`
is never consulted for live-mode agent selection -- the workflow template
assigns a real `agent_key` to each slot directly (by design, since a
template is choosing who fills a role, not discovering it), so
ADR-0020's conformance check never runs for a workflow-dispatched task.
Acceptable because a workflow template's agent assignment is an
authoring-time decision already reviewed once, not a per-task staffing
decision the way `orchestrator/staffing.py::select_agents()`'s is.

## Alternatives rejected

**A custom JSON envelope over `InvokeAgentRuntime`'s raw blob payload**
for the tool-call bridge. Rejected once `InvokeHarness`'s
`inlineFunction` tool type was found to already define exactly this
contract natively -- inventing a second one would duplicate an existing
AWS primitive for no benefit.

**Persisting `WorkflowRunner`/`WorkflowSnapshot` as metamodel entities.**
Rejected, matching `CycleReport`/`AgentRunReport`/`StaffingOutcome`'s own
precedent: orchestration-result state is a plain, in-memory shape, not a
durable graph fact the dual-twin model needs to remember forever.

**Hand-authored `ReplayAgentClient` fixtures for demo mode**, per the
original plan. Rejected during implementation -- ~28 scripted
conversations across 4 agents would have cost real effort to prove
something (the replay backend scales to a multi-agent workflow) demo
mode was never asked to prove; a scripted state machine over the
template's own declared timing/token data serves demo mode's actual
purpose (show the dashboard with zero credentials) directly.

**Doing GitHub Copilot coding agent dispatch in this same ADR.**
Rejected per the user's explicit sequencing request -- AgentCore first,
Copilot later, as a separate, focused change.
