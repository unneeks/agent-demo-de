from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from agent.planner import OllamaClient, build_goal_summary, build_plan
from agent.reflection import reflect_on_execution
from agent.tools import fix_generator, health_check, log_analyzer, metadata_lookup, verification_runner


class AgentState(TypedDict, total=False):
    user_request: str
    goal: str
    plan: list[str]
    tool_results: dict[str, Any]
    reflection: str
    fix: dict[str, Any]
    verification: dict[str, Any]
    final_answer: str
    timeline: list[dict[str, Any]]


def _format_section(title: str, body: str) -> str:
    return f"----- {title} -----\n{body.strip()}\n"


def _append_timeline(state: AgentState, phase: str, title: str, details: str, status: str = "complete") -> list[dict[str, Any]]:
    timeline = list(state.get("timeline", []))
    timeline.append(
        {
            "phase": phase,
            "title": title,
            "details": details,
            "status": status,
        }
    )
    return timeline


def understand_request(state: AgentState) -> AgentState:
    client = OllamaClient()
    goal = build_goal_summary(client, state["user_request"])
    return {
        "goal": goal,
        "timeline": _append_timeline(state, "understand_request", "Goal Understood", goal),
    }


def create_plan(state: AgentState) -> AgentState:
    client = OllamaClient()
    steps = build_plan(
        client,
        state["goal"],
        ["log_analyzer", "metadata_lookup", "health_check", "fix_generator", "verification_runner"],
    )
    return {
        "plan": steps,
        "timeline": _append_timeline(state, "create_plan", "Plan Created", " | ".join(steps)),
    }


def execute_tools(state: AgentState) -> AgentState:
    log_result = log_analyzer()
    metadata_result = metadata_lookup()
    health_result = health_check()
    return {
        "tool_results": {
            "log_analyzer": log_result,
            "metadata_lookup": metadata_result,
            "health_check": health_result,
        },
        "timeline": _append_timeline(
            state,
            "execute_tools",
            "Tools Executed",
            f"Logs: {log_result['summary']}; Metadata: {metadata_result['summary']}; Health: {health_result['summary']}",
        ),
    }


def reflect_on_results(state: AgentState) -> AgentState:
    reflection = reflect_on_execution(state["tool_results"])
    return {
        "reflection": reflection,
        "timeline": _append_timeline(state, "reflect_on_results", "Reflection Complete", reflection),
    }


def generate_fix(state: AgentState) -> AgentState:
    fix = fix_generator(
        state["tool_results"]["log_analyzer"],
        state["tool_results"]["metadata_lookup"],
        state["tool_results"]["health_check"],
    )
    return {
        "fix": fix,
        "timeline": _append_timeline(
            state,
            "generate_fix",
            "Fix Proposed",
            " | ".join(fix["actions"]),
        ),
    }


def verify_fix(state: AgentState) -> AgentState:
    verification = verification_runner(state["fix"])
    return {
        "verification": verification,
        "timeline": _append_timeline(state, "verify_fix", "Verification Simulated", verification["summary"]),
    }


def return_final_answer(state: AgentState) -> AgentState:
    tool_lines = []
    tool_lines.append(f"Log analyzer: {state['tool_results']['log_analyzer']['summary']}.")
    tool_lines.append(f"Metadata lookup: {state['tool_results']['metadata_lookup']['summary']}.")
    tool_lines.append(f"Health check: {state['tool_results']['health_check']['summary']}.")

    fix_lines = [f"- {item}" for item in state["fix"]["actions"]]
    verification_text = state["verification"]["summary"]

    final_answer = "\n".join(
        [
            _format_section("GOAL", state["goal"]),
            _format_section("PLAN", "\n".join(f"{idx}. {step}" for idx, step in enumerate(state["plan"], start=1))),
            _format_section("TOOL EXECUTION", "\n".join(tool_lines)),
            _format_section("REFLECTION", state["reflection"]),
            _format_section("FIX", f"{state['fix']['rationale']}\n" + "\n".join(fix_lines)),
            _format_section("VERIFICATION", verification_text),
            "Final Result: The nightly customer ETL failed due to executor memory exhaustion. "
            "Increase executor memory and rerun the job; the simulated verification succeeds.",
        ]
    )
    return {
        "final_answer": final_answer,
        "timeline": _append_timeline(
            state,
            "return_final_answer",
            "Final Answer Ready",
            "Agent packaged investigation summary and recommendation.",
        ),
    }


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("understand_request", understand_request)
    graph.add_node("create_plan", create_plan)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("reflect_on_results", reflect_on_results)
    graph.add_node("generate_fix", generate_fix)
    graph.add_node("verify_fix", verify_fix)
    graph.add_node("return_final_answer", return_final_answer)

    graph.set_entry_point("understand_request")
    graph.add_edge("understand_request", "create_plan")
    graph.add_edge("create_plan", "execute_tools")
    graph.add_edge("execute_tools", "reflect_on_results")
    graph.add_edge("reflect_on_results", "generate_fix")
    graph.add_edge("generate_fix", "verify_fix")
    graph.add_edge("verify_fix", "return_final_answer")
    graph.add_edge("return_final_answer", END)

    return graph.compile()
