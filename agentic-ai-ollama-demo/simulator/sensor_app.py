from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from agent.main import run_agent
from simulator.paths import LATEST_AGENT_REPORT, PIPELINE_LOG, PIPELINE_STATUS, RUNTIME_DIR
from simulator.runtime_state import (
    append_event,
    apply_fix_payload,
    load_json,
    set_approval_decision,
    set_approval_pending,
)


def _append_sensor_log(message: str) -> None:
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with PIPELINE_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} SENSOR {message}\n")


def main() -> None:
    interval = int(os.getenv("SENSOR_INTERVAL_SECONDS", "8"))
    auto_remediate = os.getenv("SENSOR_AUTO_REMEDIATE", "false").lower() == "true"
    last_seen_run = None
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        status = load_json(PIPELINE_STATUS, {})
        run_id = status.get("run_id")
        if run_id and run_id != last_seen_run:
            last_seen_run = run_id
            if status.get("status") == "failed":
                prompt = (
                    "Why did the nightly banking customer 360 dbt pipeline fail and how do we fix it? "
                    "Use the latest runtime logs and metadata."
                )
                try:
                    result = run_agent(prompt)
                    final_answer = result["final_answer"]
                    LATEST_AGENT_REPORT.write_text(final_answer, encoding="utf-8")
                    _append_sensor_log("Detected failed dbt run and generated agent remediation plan")
                    recommendation = {
                        "summary": "Increase executor memory from 4GB to 8GB and rerun the banking dbt pipeline.",
                        "executor_memory_gb": 8,
                        "actions": result["fix"]["actions"],
                        "rationale": result["fix"]["rationale"],
                    }
                    set_approval_pending(run_id, recommendation, result.get("timeline", []))
                    if auto_remediate:
                        apply_fix_payload(
                            executor_memory_gb=int(recommendation["executor_memory_gb"]),
                            source="sensor_auto_remediation",
                            approved_by="sensor_auto_remediation",
                        )
                        set_approval_decision("approved", operator="sensor_auto_remediation")
                        append_event(
                            "sensor",
                            "Auto-Remediation Applied",
                            "The sensor auto-approved the memory increase for the next cycle.",
                            severity="warning",
                            payload={"run_id": run_id, "actions": recommendation["actions"]},
                        )
                    else:
                        append_event(
                            "sensor",
                            "Human Approval Required",
                            "The agent proposed a fix and is waiting for operator approval.",
                            severity="warning",
                            payload={"run_id": run_id, "actions": recommendation["actions"]},
                        )
                except Exception as exc:
                    _append_sensor_log(f"Agent remediation failed: {exc}")
                    append_event(
                        "sensor",
                        "Agent Run Failed",
                        f"Sensor could not complete agent remediation: {exc}",
                        severity="critical",
                        payload={"run_id": run_id},
                    )
            else:
                _append_sensor_log("Observed healthy dbt pipeline run")
                append_event(
                    "sensor",
                    "Sensor Observed Healthy Run",
                    "No intervention was required for the latest banking pipeline cycle.",
                    severity="success",
                    payload={"run_id": run_id},
                )
        time.sleep(interval)


if __name__ == "__main__":
    main()
