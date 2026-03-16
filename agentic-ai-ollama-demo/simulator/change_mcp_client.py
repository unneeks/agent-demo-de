from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def call_change_mcp(method: str, params: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"method": method, "params": params})
    completed = subprocess.run(
        [sys.executable, "-m", "simulator.change_mcp_server"],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"MCP tool call failed for method '{method}'.")

    response = json.loads(completed.stdout or "{}")
    if not response.get("ok"):
        raise RuntimeError(response.get("error", f"MCP tool call failed for method '{method}'."))
    return response["result"]
