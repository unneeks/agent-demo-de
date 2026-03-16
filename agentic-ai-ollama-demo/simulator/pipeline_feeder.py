from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone

from simulator.dataset_generator import generate_dataset
from simulator.paths import CURRENT_JOB_METADATA, DBT_DIR, FIX_STATE, PIPELINE_LOG, PIPELINE_STATUS, RUNTIME_DIR, SCENARIO_STATE


def _load_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def _append_log(message: str) -> None:
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    PIPELINE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PIPELINE_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def _write_status(payload: dict[str, object]) -> None:
    PIPELINE_STATUS.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _dbt_cmd(command: list[str], force_memory_error: bool) -> subprocess.CompletedProcess[str]:
    vars_payload = json.dumps({"force_memory_error": force_memory_error})
    full_command = command + ["--vars", vars_payload]
    return subprocess.run(
        full_command,
        cwd=DBT_DIR,
        text=True,
        capture_output=True,
        check=False,
    )


def run_cycle() -> None:
    scenario = _load_json(SCENARIO_STATE, {})
    if not scenario:
        scenario = generate_dataset("memory_stress")
    fix_state = _load_json(FIX_STATE, {"executor_memory_gb": 4, "status": "not_applied"})

    scenario_name = scenario["scenario"]
    fix_applied = fix_state.get("executor_memory_gb", 4) >= 8
    force_memory_error = bool(scenario.get("force_memory_error")) and not fix_applied

    run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _append_log(f"INFO scheduler: Starting dbt banking pipeline run_id={run_id} scenario={scenario_name}")
    _append_log("INFO dataset_loader: Banking entities refreshed from generated demo seeds")

    seed_result = _dbt_cmd(["dbt", "seed", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)], False)
    run_result = _dbt_cmd(["dbt", "run", "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)], force_memory_error)

    seed_output = (seed_result.stdout + "\n" + seed_result.stderr).strip()
    run_output = (run_result.stdout + "\n" + run_result.stderr).strip()

    if seed_output:
        _append_log(f"INFO dbt.seed: {seed_output.splitlines()[-1]}")

    status = "succeeded"
    summary = "dbt run completed successfully for the banking customer 360 pipeline."
    if run_result.returncode != 0:
        status = "failed"
        summary = "dbt run failed during the high-volume banking transformation."
        _append_log("WARN spark.executor: Executor memory overhead exceeded threshold on customer_360 model")
        _append_log("ERROR spark.executor: java.lang.OutOfMemoryError: Java heap space")
        _append_log("ERROR pipeline: dbt model mart_customer_360 failed with worker memory exhaustion")
    else:
        _append_log("INFO pipeline: dbt model mart_customer_360 finished successfully")
        _append_log("INFO pipeline: dbt model fct_account_activity finished successfully")

    _append_log(f"INFO pipeline: run_id={run_id} status={status}")

    metadata = _load_json(CURRENT_JOB_METADATA, {})
    _write_status(
        {
            "run_id": run_id,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "scenario": scenario_name,
            "status": status,
            "summary": summary,
            "force_memory_error": force_memory_error,
            "fix_applied": fix_applied,
            "metadata": metadata,
            "dbt_output_tail": run_output.splitlines()[-20:],
        }
    )


def main() -> None:
    interval = int(os.getenv("PIPELINE_INTERVAL_SECONDS", "20"))
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if not SCENARIO_STATE.exists():
        generate_dataset(os.getenv("PIPELINE_DEFAULT_SCENARIO", "memory_stress"))

    while True:
        run_cycle()
        time.sleep(interval)


if __name__ == "__main__":
    main()
