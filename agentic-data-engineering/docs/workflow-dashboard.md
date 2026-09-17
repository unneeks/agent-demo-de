# Live Workflow Dashboard

A live, pollable view of several agents progressing through a delivery
model's real phases at once -- the capability `docs/web-ui.md` named as
missing ("no cycle/agent-run history") and `run_cycle()`'s one-shot
report shape can't provide on its own. See
[ADR-0023](adr/0023-agentcore-harness-and-live-workflow-dashboard.md) for
the full reasoning and the alternatives rejected.

## The one idea that must not be compromised

**`AgentCoreHarnessClient` is *just* a fourth `AgentLLMClient`.** It adds
no new orchestration primitive. `agent_runtime.loop.run_agent()`'s
existing dispatch loop (call the model → resolve any tool calls → execute
→ append the result → call again) already implements "the harness returns
a typed tool-call message, the orchestrator runs it locally, then resumes
the harness" -- a new backend only has to speak the Protocol
(`next_turn(*, system_prompt, messages, tools) -> AgentTurnResult`) and
translate between AWS AgentCore's content-block dialect and this
platform's own (Anthropic-shaped) transcript. Nothing in
`orchestrator/workflow.py` or `webui/` needs to know which backend a
given agent slot is using.

## Two modes

- **Demo** -- a scripted state machine, zero credentials. Each work
  product progresses through the same states a live run would
  (`not_started → in_progress → completed`), timed and token-costed by
  `metamodel-registry/workflow_templates.yaml`'s own declared
  `demo_duration_seconds`/`demo_tokens` (registry data, not invented
  Python literals). It does **not** invoke `run_agent()` at all -- a
  deliberate simplification from the original plan, which had proposed
  driving demo mode through `ReplayAgentClient` fixtures. Hand-authoring
  ~28 scripted conversations across 4 agents would have cost real effort
  to prove something demo mode was never asked to prove (that the replay
  backend scales to a whole workflow); demo mode exists to show the
  dashboard with no credentials, and a scripted state machine does that
  directly.
- **Live** -- each work product is one real `run_agent()` call, against
  whichever `AgentLLMClient` (`AgentCoreHarnessClient`, `Anthropic
  AgentClient`, `CopilotCliAgentClient`) and `ToolExecutor`
  (`LocalToolExecutor`, falling back to `SimulatedToolExecutor` for
  actions it doesn't implement for real) the caller configures per agent
  slot via `POST /api/workflows`'s `live_backend`/`live_agent_backends`.

## AgentCore, specifically

`AgentCoreHarnessClient` calls `boto3.client("bedrock-agentcore").
invoke_harness(harnessArn=..., runtimeSessionId=..., messages=...,
tools=..., model=..., maxIterations=1)`. Verified directly against the
real, installed `botocore` service model (not scraped docs, several of
which were unreachable from this environment) --
`HarnessInlineFunctionConfig`'s own documentation states plainly:
*"When the agent calls this tool, the tool call is returned to the caller
for external execution."* That is the AWS-native version of the
client-side tool bridge this platform needed; no custom envelope was
invented on top of it.

- **Credentials**: the ambient boto3 default chain only (env vars,
  `~/.aws/config`/`credentials`, SSO cache, IMDS) -- whatever `aws sso
  login`/`aws configure` already set up on the machine running this app.
  No AWS key is ever accepted as a request field or constructed in code.
- **Session continuity**: one `runtimeSessionId` (a UUID) generated once
  per client instance, reused across every `next_turn()` call on it --
  the "resume the harness from where it stopped" the platform needs.
- **Metrics**: `HarnessMetadataEvent.usage`
  (`inputTokens`/`outputTokens`/`totalTokens`) and `.metrics.latencyMs`
  are the real numbers behind the dashboard's token-cost/elapsed-time
  figures -- not estimated, not invented, read directly off AgentCore's
  own streamed response. (Estimated in USD via a small, explicit,
  overridable $/1K-token table, labelled as an estimate in the UI --
  AgentCore doesn't bill in dollars per call, so this part genuinely is a
  coarse proxy, same "coarse, honestly labelled" discipline
  `docs/gap-analysis.md` already established.)
- **Never live-verified against a real AWS account** -- no AWS
  credentials exist in the environment this was built in. Covered by
  unit tests against a stubbed `boto3` client
  (`tests/unit/test_agentcore_client.py`): request shape, response-stream
  parsing, session continuity, error mapping. Treat this the same way
  `docs/agent-runtime.md` already treats `AnthropicAgentClient`/
  `CopilotCliAgentClient` -- built correctly against the real documented
  shape, not proven against a live call.

## The local tool bridge

`LocalToolExecutor` (`agent_runtime/local_tool_executor.py`) runs on the
same machine as the web app -- "the developer machine" a returned
`inlineFunction` tool call needs. Real for `git.read_repository`/
`pytest.run_tests` (subprocess) and `github.read_pull_request`/
`github.comment_on_pull_request` (the `gh` CLI, the same binary
`discovery/extraction/copilot_cli_client.py` and
`scripts/onboard_project.py` already standardize on). Everything else in
the catalog (`neo4j.traverse`, `bigquery.profile_query`,
`modeling-tool.*`, `metadata-platform.*`, `github.copilot_code_review`)
has no generic developer-machine realization -- it delegates to a
caller-supplied `fallback` executor (typically `SimulatedToolExecutor`)
or raises `UnknownToolActionError`, never a fabricated response.

## The workflow template

One ships today: `data-engineering-sdlc`
(`metamodel-registry/workflow_templates.yaml`), matching the reference
dashboard's 5-phase bar (Requirements/Design/Build/Test/Release) and 4
agent cards. Agent-to-slot assignment is the template's own authoring
decision (`agent_key` named directly), **not** a `resolve_role()`-derived
staffing outcome -- a workflow template is choosing which real catalog
agent fills a role by design, not discovering one. Three slots reuse
already-staffed catalog agents (`data-model-composer`, `regression-agent`,
`delivery-compliance-agent`); one new agent
(`requirements-analyst-agent`) was added for the one slot with no
existing fit -- a near-miss against `requirements-engineer`'s full stated
requirements (the skills catalog has no `feasibility-analysis` skill
yet), which is fine here since a workflow dispatch never calls
`resolve_role()`.

Work products are named after the reference dashboard's own visible
content, and where a genuine match exists, carry the delivery model's
real `task_key` (e.g. "Stakeholder Requirements" → `task.business-
requirements`); where none does, `task_key: null` names it honestly as
illustrative dashboard data, not a registered `DeliveryTask`.

## Human attention and approval

A denied tool call (an approval gate, or an unresolved/hallucinated tool
name) pauses that agent slot; the dashboard's snapshot surfaces it in
`human_attention` with the real reason. `POST /api/workflows/{run_id}/
approve` retries the same work product with an elevated `ApprovalLevel`.
**This is not a true mid-turn pause/resume of a live model call** --
nothing in `run_agent()` supports suspending a running call across HTTP
requests. It is a fresh `run_agent()` call for the same work product,
started at a higher granted approval.

## Errors

| Error | Raised when |
|---|---|
| `UnknownWorkflowTemplateError` (404) | `POST /api/workflows` names a `template_key` not in the loaded catalog |
| `UnknownWorkflowRunError` (404) | A request names a `run_id` this server process has no record of -- runs are in-memory only |
| `MissingWorkflowBackendError` (422) | A live run is requested without a `live_backend`/per-slot override for some agent slot |
| `WorkflowTemplateError` | `workflow_templates.yaml` names an unknown `agent_key`/`phase_key` -- caught at load time, not a later `KeyError` |
| `AgentRuntimeError` (502) | The configured backend's call fails (a missing `harness_arn`, an unreachable AWS account, `gh`/boto3 not installed, ...) |

## What this is not

- **No GitHub Copilot coding agent dispatch** -- `Agent.execution_model
  == EXTERNAL_AGENT` stays registered-but-unexecuted, exactly as it was
  before this change (ADR-0014). A deliberate sequencing choice, not an
  oversight.
- **No true async pause/resume of a live model call.** "Approve and
  retry" is a fresh `run_agent()` call, not a suspended one.
- **No persistence across a server restart.** `app.state.workflow_runs`
  is an in-memory `dict`; every run's progress is gone when the process
  exits.
- **No `resolve_role()`/staffing-chain resolution for a workflow's agent
  assignment.** A template names its agents directly.
- **No full catalog coverage in `LocalToolExecutor`.** 4 of 11 catalog
  actions have a real implementation; the rest need a fallback executor.
- **No live-mode start form in the HTML dashboard.** `/workflows`'s form
  only starts demo runs; a live run's backend config is only reachable
  via `POST /api/workflows`.
