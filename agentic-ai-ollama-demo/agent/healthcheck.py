from __future__ import annotations

from typing import Any


def run_health_check() -> dict[str, Any]:
    """Simulate infrastructure checks for a data platform."""
    return {
        "database_connectivity": "healthy",
        "warehouse_latency_ms": 42,
        "disk_usage_percent": 61,
        "scheduler_status": "healthy",
        "executor_memory_pressure": "high",
        "summary": "Core services are healthy, but workers show high memory pressure during the ETL window.",
    }
