from __future__ import annotations

import argparse
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.agent_graph import build_agent_graph
from simulator.change_mcp_client import call_change_mcp
from simulator.dataset_generator import generate_dataset
from simulator.paths import AGENT_RUN_STATE, APPROVAL_STATE, CHANGE_RECORDS_STATE, CURRENT_JOB_METADATA, PIPELINE_STATUS, ROOT_DIR, SCENARIO_STATE
from simulator.scenarios import SCENARIOS
from simulator.runtime_state import (
    append_event,
    apply_fix_payload,
    load_json,
    read_event_tail,
    read_log_tail,
    reset_incident_state,
    request_pipeline_trigger,
    set_approval_decision,
    write_agent_run_state,
)


UI_DIR = ROOT_DIR / "ui"

app = FastAPI(title="Agentic AI Ollama Demo", version="2.0.0")
agent_graph = build_agent_graph()

if UI_DIR.exists():
    app.mount("/assets", StaticFiles(directory=UI_DIR), name="assets")


class RunRequest(BaseModel):
    prompt: str


class ApprovalRequest(BaseModel):
    operator: str = "human_operator"


class ScenarioRequest(BaseModel):
    scenario: str
    reset_incident: bool = True
    trigger_now: bool = True
    operator: str = "web_operator"


def _build_dashboard_payload() -> dict[str, Any]:
    pipeline = load_json(PIPELINE_STATUS, {"status": "idle"})
    scenario = load_json(SCENARIO_STATE, {"scenario": "not_loaded"})
    approval = load_json(APPROVAL_STATE, {"status": "idle"})
    agent_run = load_json(AGENT_RUN_STATE, {"status": "idle"})
    metadata = load_json(CURRENT_JOB_METADATA, {})
    change_records = load_json(CHANGE_RECORDS_STATE, [])

    return {
        "pipeline": pipeline,
        "scenario": scenario,
        "approval": approval,
        "agent_run": agent_run,
        "metadata": metadata,
        "change_records": change_records[-10:],
        "events": read_event_tail(),
        "log_tail": read_log_tail(),
    }


def run_agent(prompt: str) -> dict[str, Any]:
    if not prompt.strip():
        raise ValueError("Prompt must not be empty.")

    try:
        result = agent_graph.invoke({"user_request": prompt})
        payload = {
            "status": "complete",
            "prompt": prompt,
            "goal": result.get("goal"),
            "plan": result.get("plan", []),
            "timeline": result.get("timeline", []),
            "fix": result.get("fix", {}),
            "verification": result.get("verification", {}),
            "final_answer": result.get("final_answer", ""),
        }
        write_agent_run_state(payload)
        append_event(
            "agent",
            "Agent Investigation Completed",
            "The LangGraph workflow completed and returned a remediation summary.",
            severity="info",
            payload={"timeline_count": len(payload["timeline"])},
        )
    except Exception as exc:
        append_event(
            "agent",
            "Agent Investigation Failed",
            f"FastAPI agent workflow execution failed: {exc}",
            severity="critical",
        )
        raise RuntimeError(
            "Agent execution failed. Ensure Ollama is reachable and the configured model is pulled."
        ) from exc
    return result


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b")}


@app.get("/api/dashboard")
def dashboard_state() -> dict[str, Any]:
    return _build_dashboard_payload()


@app.post("/api/run")
@app.post("/run")
def run(request: RunRequest) -> dict[str, Any]:
    try:
        return run_agent(request.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/approval/approve")
def approve_fix(request: ApprovalRequest) -> dict[str, Any]:
    approval = load_json(APPROVAL_STATE, {"status": "idle"})
    recommendation = approval.get("recommendation")
    if approval.get("status") != "pending" or not recommendation:
        raise HTTPException(status_code=409, detail="No pending fix recommendation is waiting for approval.")

    metadata = load_json(CURRENT_JOB_METADATA, {})
    run_id = approval.get("run_id")
    created_record = call_change_mcp(
        "create_change_record",
        {
            "service": "dbt_banking_pipeline",
            "job_name": metadata.get("job_name", "current_pipeline"),
            "domain": metadata.get("domain", "data platform"),
            "run_id": run_id,
            "risk": "medium",
            "summary": recommendation.get("summary", "Apply remediation for the failed pipeline run."),
            "rationale": recommendation.get("rationale", "No rationale supplied."),
            "implementation_plan": recommendation.get("actions", []),
            "proposed_fix": {
                "executor_memory_gb": int(recommendation.get("executor_memory_gb", 8)),
                "actions": recommendation.get("actions", []),
            },
            "requested_by": request.operator,
        },
    )
    approved_record = call_change_mcp(
        "approve_change_record",
        {"change_id": created_record["change_id"], "operator": request.operator},
    )

    fix_state = apply_fix_payload(
        executor_memory_gb=int(recommendation.get("executor_memory_gb", 8)),
        source=f"approved_change_record:{approved_record['change_id']}",
        approved_by=request.operator,
    )
    approval = set_approval_decision("approved", operator=request.operator, change_record=approved_record)
    append_event(
        "approval",
        "Change Record Raised",
        f"Approved remediation created change record {created_record['change_id']} for execution governance.",
        severity="info",
        payload={"operator": request.operator, "change_id": created_record["change_id"], "run_id": run_id},
    )
    append_event(
        "approval",
        "Change Auto-Approved",
        f"Change record {approved_record['change_id']} was auto-approved after human remediation approval.",
        severity="success",
        payload={"operator": request.operator, "change_id": approved_record["change_id"], "run_id": run_id},
    )
    append_event(
        "approval",
        "Fix Applied",
        f"Approved change record {approved_record['change_id']} armed the fix for the next pipeline cycle.",
        severity="success",
        payload={
            "operator": request.operator,
            "change_id": approved_record["change_id"],
            "executor_memory_gb": fix_state["executor_memory_gb"],
        },
    )
    return {"approval": approval, "fix_state": fix_state, "change_record": approved_record}


@app.post("/api/approval/reject")
def reject_fix(request: ApprovalRequest) -> dict[str, Any]:
    approval = load_json(APPROVAL_STATE, {"status": "idle"})
    if approval.get("status") != "pending":
        raise HTTPException(status_code=409, detail="No pending fix recommendation is waiting for approval.")

    approval = set_approval_decision("rejected", operator=request.operator)
    append_event(
        "approval",
        "Fix Rejected",
        "Operator rejected the remediation proposal before any change record was created.",
        severity="warning",
        payload={"operator": request.operator},
    )
    return {"approval": approval}


@app.post("/api/reset")
def reset_incident(request: ApprovalRequest) -> dict[str, Any]:
    reset_incident_state()
    append_event(
        "operator",
        "Incident State Reset",
        "Operator cleared runtime approvals, agent traces, and fix state for a fresh demo cycle.",
        severity="info",
        payload={"operator": request.operator},
    )
    return {"status": "reset"}


@app.post("/api/scenario/load")
def load_scenario(request: ScenarioRequest) -> dict[str, Any]:
    if request.scenario not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{request.scenario}'.")

    if request.reset_incident:
        reset_incident_state()

    scenario_payload = generate_dataset(request.scenario)
    if request.trigger_now:
        request_pipeline_trigger(f"scenario:{request.scenario}")

    append_event(
        "operator",
        "Scenario Loaded",
        f"Operator loaded scenario '{request.scenario}' for the next pipeline cycle.",
        severity="info",
        payload={"scenario": request.scenario, "trigger_now": request.trigger_now, "operator": request.operator},
    )
    return {"scenario": scenario_payload}


def cli() -> None:
    parser = argparse.ArgumentParser(description="Run the local agentic AI demo.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Why did the nightly customer ETL job fail and how do we fix it?",
        help="The user request for the agent to investigate.",
    )
    args = parser.parse_args()

    result = run_agent(args.prompt)
    print(result["final_answer"])


if __name__ == "__main__":
    cli()
