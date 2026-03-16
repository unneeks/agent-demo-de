from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any

from simulator.paths import CHANGE_RECORDS_STATE
from simulator.runtime_state import load_json, write_json


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _load_records() -> list[dict[str, Any]]:
    return load_json(CHANGE_RECORDS_STATE, [])


def _write_records(records: list[dict[str, Any]]) -> None:
    write_json(CHANGE_RECORDS_STATE, records)


def _find_record(records: list[dict[str, Any]], change_id: str) -> dict[str, Any]:
    for record in records:
        if record.get("change_id") == change_id:
            return record
    raise ValueError(f"Unknown change record '{change_id}'.")


def create_change_record(params: dict[str, Any]) -> dict[str, Any]:
    records = _load_records()
    next_index = len(records) + 1
    change_id = f"CHG-{next_index:04d}"
    record = {
        "change_id": change_id,
        "status": "pending_approval",
        "created_at": _now_iso(),
        "service": params.get("service", "pipeline"),
        "job_name": params.get("job_name", "unknown_job"),
        "domain": params.get("domain", "data platform"),
        "run_id": params.get("run_id"),
        "risk": params.get("risk", "medium"),
        "summary": params.get("summary", "Apply remediation for a failed pipeline run."),
        "rationale": params.get("rationale", "No rationale supplied."),
        "implementation_plan": params.get("implementation_plan", []),
        "rollback_plan": params.get(
            "rollback_plan",
            [
                "Revert the configuration override.",
                "Restore the previous execution profile.",
                "Requeue the pipeline with the prior settings if rollback is required.",
            ],
        ),
        "proposed_fix": params.get("proposed_fix", {}),
        "requested_by": params.get("requested_by", "agent_sensor"),
    }
    records.append(record)
    _write_records(records)
    return record


def approve_change_record(params: dict[str, Any]) -> dict[str, Any]:
    records = _load_records()
    record = _find_record(records, params["change_id"])
    record["status"] = "approved"
    record["approved_at"] = _now_iso()
    record["approved_by"] = params.get("operator", "human_operator")
    _write_records(records)
    return record


def reject_change_record(params: dict[str, Any]) -> dict[str, Any]:
    records = _load_records()
    record = _find_record(records, params["change_id"])
    record["status"] = "rejected"
    record["rejected_at"] = _now_iso()
    record["rejected_by"] = params.get("operator", "human_operator")
    record["rejection_reason"] = params.get("reason", "Operator rejected the proposed change.")
    _write_records(records)
    return record


def get_change_record(params: dict[str, Any]) -> dict[str, Any]:
    records = _load_records()
    return _find_record(records, params["change_id"])


METHODS = {
    "create_change_record": create_change_record,
    "approve_change_record": approve_change_record,
    "reject_change_record": reject_change_record,
    "get_change_record": get_change_record,
}


def main() -> None:
    request = json.loads(sys.stdin.read() or "{}")
    method = request.get("method")
    params = request.get("params", {})
    if method not in METHODS:
        response = {"ok": False, "error": f"Unsupported MCP method '{method}'."}
    else:
        try:
            response = {"ok": True, "result": METHODS[method](params)}
        except Exception as exc:  # pragma: no cover - defensive CLI wrapper
            response = {"ok": False, "error": str(exc)}
    sys.stdout.write(json.dumps(response))


if __name__ == "__main__":
    main()
