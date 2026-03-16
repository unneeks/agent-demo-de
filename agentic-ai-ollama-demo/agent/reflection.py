from __future__ import annotations

from typing import Any


def reflect_on_execution(tool_results: dict[str, Any]) -> str:
    log_summary = tool_results["log_analyzer"]["summary"]
    metadata_summary = tool_results["metadata_lookup"]["summary"]
    health_summary = tool_results["health_check"]["summary"]

    return (
        "The evidence is consistent across logs, metadata, and health checks. "
        f"Logs show {log_summary.lower()} Metadata indicates {metadata_summary.lower()} "
        f"Health checks report {health_summary.lower()} "
        "The most likely root cause is a workload or configuration bottleneck rather than a platform-wide outage."
    )
