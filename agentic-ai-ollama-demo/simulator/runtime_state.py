from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from simulator.paths import AGENT_RUN_STATE, APPROVAL_STATE, EVENT_LOG, FIX_STATE, LATEST_AGENT_REPORT, PIPELINE_LOG, PIPELINE_TRIGGER, RUNTIME_DIR


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    ensure_runtime_dir()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_event(kind: str, title: str, details: str, severity: str = "info", payload: dict[str, Any] | None = None) -> None:
    ensure_runtime_dir()
    event = {
        "timestamp": now_iso(),
        "kind": kind,
        "title": title,
        "details": details,
        "severity": severity,
        "payload": payload or {},
    }
    with EVENT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def read_event_tail(limit: int = 40) -> list[dict[str, Any]]:
    if not EVENT_LOG.exists():
        return []
    lines = EVENT_LOG.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[-limit:] if line.strip()]


def write_agent_run_state(payload: dict[str, Any]) -> None:
    write_json(AGENT_RUN_STATE, payload)


def set_approval_pending(run_id: str, recommendation: dict[str, Any], timeline: list[dict[str, Any]]) -> None:
    payload = {
        "status": "pending",
        "run_id": run_id,
        "requested_at": now_iso(),
        "recommendation": recommendation,
        "timeline": timeline,
    }
    write_json(APPROVAL_STATE, payload)


def set_approval_decision(status: str, operator: str = "human_operator") -> dict[str, Any]:
    approval = load_json(APPROVAL_STATE, {"status": "idle"})
    approval["status"] = status
    approval["decided_at"] = now_iso()
    approval["operator"] = operator
    write_json(APPROVAL_STATE, approval)
    return approval


def clear_approval_state() -> None:
    if APPROVAL_STATE.exists():
        APPROVAL_STATE.unlink()


def apply_fix_payload(executor_memory_gb: int, source: str, approved_by: str = "human_operator") -> dict[str, Any]:
    payload = {
        "status": "applied",
        "applied_at": now_iso(),
        "executor_memory_gb": executor_memory_gb,
        "source": source,
        "approved_by": approved_by,
    }
    write_json(FIX_STATE, payload)
    return payload


def read_log_tail(limit: int = 60) -> list[str]:
    if not PIPELINE_LOG.exists():
        return []
    return PIPELINE_LOG.read_text(encoding="utf-8").splitlines()[-limit:]


def reset_incident_state() -> None:
    for path in (FIX_STATE, APPROVAL_STATE, AGENT_RUN_STATE, LATEST_AGENT_REPORT, EVENT_LOG):
        if path.exists():
            path.unlink()


def request_pipeline_trigger(reason: str) -> None:
    write_json(
        PIPELINE_TRIGGER,
        {
            "requested_at": now_iso(),
            "reason": reason,
        },
    )


def consume_pipeline_trigger() -> dict[str, Any] | None:
    if not PIPELINE_TRIGGER.exists():
        return None
    payload = load_json(PIPELINE_TRIGGER, {})
    PIPELINE_TRIGGER.unlink(missing_ok=True)
    return payload
