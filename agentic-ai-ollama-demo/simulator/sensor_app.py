from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from agent.main import run_agent
from simulator.paths import FIX_STATE, LATEST_AGENT_REPORT, PIPELINE_LOG, PIPELINE_STATUS, RUNTIME_DIR


def _load_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def _append_sensor_log(message: str) -> None:
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with PIPELINE_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} SENSOR {message}\n")


def _apply_fix(agent_output: str) -> None:
    fix_payload = {
        "status": "applied",
        "applied_at": datetime.now(tz=timezone.utc).isoformat(),
        "executor_memory_gb": 8 if "Increase Spark executor memory from 4GB to 8GB." in agent_output else 4,
        "source": "sensor_auto_remediation",
    }
    FIX_STATE.write_text(json.dumps(fix_payload, indent=2), encoding="utf-8")


def main() -> None:
    interval = int(os.getenv("SENSOR_INTERVAL_SECONDS", "8"))
    auto_remediate = os.getenv("SENSOR_AUTO_REMEDIATE", "true").lower() == "true"
    last_seen_run = None
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        status = _load_json(PIPELINE_STATUS, {})
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
                    if auto_remediate:
                        _apply_fix(final_answer)
                        _append_sensor_log("Applied simulated fix: increased executor memory for next cycle")
                except Exception as exc:
                    _append_sensor_log(f"Agent remediation failed: {exc}")
            else:
                _append_sensor_log("Observed healthy dbt pipeline run")
        time.sleep(interval)


if __name__ == "__main__":
    main()
