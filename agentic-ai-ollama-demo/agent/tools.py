from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.healthcheck import run_health_check


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RUNTIME_DIR = ROOT_DIR / "runtime"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def log_analyzer() -> dict[str, Any]:
    log_path = RUNTIME_DIR / "pipeline.log"
    if not log_path.exists():
        log_path = DATA_DIR / "sample_pipeline_logs.txt"
    log_text = log_path.read_text(encoding="utf-8")
    relevant_lines = [
        line for line in log_text.splitlines() if any(token in line for token in ("ERROR", "WARN", "OOM", "exit code"))
    ]
    memory_failure = "Java heap space" in log_text or "OOMKilled" in log_text
    summary = (
        "the nightly customer ETL failed because the transform step exhausted executor memory"
        if memory_failure
        else "no memory issue detected in the logs"
    )
    return {
        "memory_failure": memory_failure,
        "summary": summary,
        "relevant_lines": relevant_lines,
        "log_path": str(log_path),
    }


def metadata_lookup() -> dict[str, Any]:
    metadata_path = RUNTIME_DIR / "current_job_metadata.json"
    if not metadata_path.exists():
        metadata_path = DATA_DIR / "sample_job_metadata.json"
    payload = _read_json(metadata_path)
    dependencies = payload.get("upstream_dependencies", [])
    summary = (
        f"the job {payload['job_name']} depends on {', '.join(dependencies)} and runs a heavy customer aggregation"
    )
    return {
        "job_name": payload["job_name"],
        "schedule": payload["schedule"],
        "owner": payload["owner"],
        "executor_memory_gb": payload["runtime"]["executor_memory_gb"],
        "retry_policy": payload["runtime"]["retry_policy"],
        "summary": summary,
        "raw": payload,
        "metadata_path": str(metadata_path),
    }


def health_check() -> dict[str, Any]:
    payload = run_health_check()
    fix_state_path = RUNTIME_DIR / "fix_state.json"
    if fix_state_path.exists():
        payload["fix_state"] = _read_json(fix_state_path)
    return payload


def fix_generator(log_result: dict[str, Any], metadata_result: dict[str, Any], health_result: dict[str, Any]) -> dict[str, Any]:
    increase_from = metadata_result["executor_memory_gb"]
    increase_to = max(increase_from * 2, 8)
    actions = [
        f"Increase Spark executor memory from {increase_from}GB to {increase_to}GB.",
        "Keep the current retry policy but trigger an immediate rerun after the config update.",
        "Monitor worker memory pressure during the next nightly window.",
    ]
    rationale = (
        "The transform stage failed with heap exhaustion while platform services remained healthy, "
        "so the lowest-risk fix is to raise executor memory and rerun the batch."
    )
    return {
        "actions": actions,
        "rationale": rationale,
        "health_context": health_result["summary"],
    }


def verification_runner(fix_result: dict[str, Any]) -> dict[str, Any]:
    actions = fix_result["actions"]
    return {
        "success": True,
        "applied_actions": actions,
        "summary": "Simulated rerun completed successfully. The nightly customer ETL finished after increasing executor memory.",
        "job_status": "succeeded",
        "rows_processed": 12480593,
    }
