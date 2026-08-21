"""Agent runtime -- the one layer `docs/architecture.md`'s layered diagram
still marked `(later)` through Phase 6. `run_agent()` is a real multi-turn
planner-executor loop calling a real `AgentLLMClient` backend; every tool
call is answered by `SimulatedToolExecutor`, so no real side effect ever
occurs. See docs/agent-runtime.md.
"""

from agent_runtime.approval import ApprovalDecision, ApprovalPolicy, AutomationLevelApprovalPolicy
from agent_runtime.context import build_agent_context, render_system_prompt
from agent_runtime.errors import AgentRuntimeError, FixtureExhaustedError, UnknownToolActionError
from agent_runtime.llm import AgentLLMClient, AgentTurnResult
from agent_runtime.loop import run_agent
from agent_runtime.result import AgentRunReport, AgentTurn, ToolCallRecord
from agent_runtime.simulated_tools import SimulatedToolExecutor
from agent_runtime.tools import ToolCallRequest, ToolDefinition, ToolExecutor, build_tool_definitions

__all__ = [
    "AgentLLMClient",
    "AgentRunReport",
    "AgentRuntimeError",
    "AgentTurn",
    "AgentTurnResult",
    "ApprovalDecision",
    "ApprovalPolicy",
    "AutomationLevelApprovalPolicy",
    "FixtureExhaustedError",
    "SimulatedToolExecutor",
    "ToolCallRecord",
    "ToolCallRequest",
    "ToolDefinition",
    "ToolExecutor",
    "UnknownToolActionError",
    "build_agent_context",
    "build_tool_definitions",
    "render_system_prompt",
    "run_agent",
]
