from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone

from simulator.dataset_generator import generate_dataset
from simulator.paths import CURRENT_JOB_METADATA, DBT_DIR, FIX_STATE, PIPELINE_LOG, PIPELINE_STATUS, RUNTIME_DIR, SCENARIO_STATE
from simulator.runtime_state import append_event, clear_approval_state, consume_pipeline_trigger, load_json, write_json


def _append_log(message: str) -> None:
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    PIPELINE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PIPELINE_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def _write_status(payload: dict[str, object]) -> None:
    write_json(PIPELINE_STATUS, payload)


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
    scenario = load_json(SCENARIO_STATE, {})
    if not scenario:
        scenario = generate_dataset("memory_stress")
    fix_state = load_json(FIX_STATE, {"executor_memory_gb": 4, "status": "not_applied"})

    scenario_name = scenario["scenario"]
    fix_applied = fix_state.get("executor_memory_gb", 4) >= 8
    force_memory_error = bool(scenario.get("force_memory_error")) and not fix_applied

    run_id = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _append_log(f"INFO scheduler: Starting dbt banking pipeline run_id={run_id} scenario={scenario_name}")
    _append_log("INFO dataset_loader: Banking entities refreshed from generated demo seeds")
    append_event("pipeline", "Pipeline Cycle Started", f"dbt run {run_id} started for scenario {scenario_name}.")

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
        append_event(
            "pipeline",
            "Critical Pipeline Failure",
            "mart_customer_360 crashed with simulated memory exhaustion.",
            severity="critical",
            payload={"run_id": run_id, "scenario": scenario_name},
        )
    else:
        _append_log("INFO pipeline: dbt model mart_customer_360 finished successfully")
        _append_log("INFO pipeline: dbt model fct_account_activity finished successfully")
        clear_approval_state()
        append_event(
            "pipeline",
            "Pipeline Recovery",
            "Banking dbt models completed successfully.",
            severity="success",
            payload={"run_id": run_id, "scenario": scenario_name},
        )

    _append_log(f"INFO pipeline: run_id={run_id} status={status}")

    metadata = load_json(CURRENT_JOB_METADATA, {})
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
        slept = 0
        while slept < interval:
            trigger = consume_pipeline_trigger()
            if trigger:
                append_event(
                    "pipeline",
                    "Immediate Cycle Triggered",
                    f"Operator requested an immediate pipeline run: {trigger.get('reason', 'manual trigger')}.",
                    severity="info",
                )
                break
            time.sleep(1)
            slept += 1


if __name__ == "__main__":
    main()
