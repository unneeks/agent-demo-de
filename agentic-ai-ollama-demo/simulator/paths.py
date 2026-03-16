from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RUNTIME_DIR = ROOT_DIR / "runtime"
DBT_DIR = ROOT_DIR / "dbt_demo"
GENERATED_SEEDS_DIR = DBT_DIR / "seeds" / "generated"

PIPELINE_LOG = RUNTIME_DIR / "pipeline.log"
PIPELINE_STATUS = RUNTIME_DIR / "pipeline_status.json"
FIX_STATE = RUNTIME_DIR / "fix_state.json"
SCENARIO_STATE = RUNTIME_DIR / "scenario.json"
LATEST_AGENT_REPORT = RUNTIME_DIR / "latest_agent_report.txt"
CURRENT_JOB_METADATA = RUNTIME_DIR / "current_job_metadata.json"
AGENT_RUN_STATE = RUNTIME_DIR / "agent_run_state.json"
APPROVAL_STATE = RUNTIME_DIR / "approval_state.json"
EVENT_LOG = RUNTIME_DIR / "event_log.jsonl"
PIPELINE_TRIGGER = RUNTIME_DIR / "pipeline_trigger.json"
CHANGE_RECORDS_STATE = RUNTIME_DIR / "change_records.json"
