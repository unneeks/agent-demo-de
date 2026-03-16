from __future__ import annotations

import argparse
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent.agent_graph import build_agent_graph


app = FastAPI(title="Agentic AI Ollama Demo", version="1.0.0")
agent_graph = build_agent_graph()


class RunRequest(BaseModel):
    prompt: str


def run_agent(prompt: str) -> dict[str, Any]:
    if not prompt.strip():
        raise ValueError("Prompt must not be empty.")

    try:
        result = agent_graph.invoke({"user_request": prompt})
    except Exception as exc:
        raise RuntimeError(
            "Agent execution failed. Ensure Ollama is reachable and the configured model is pulled."
        ) from exc
    return result


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b")}


@app.post("/run")
def run(request: RunRequest) -> dict[str, Any]:
    try:
        return run_agent(request.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def cli() -> None:
    parser = argparse.ArgumentParser(description="Run the local agentic AI demo.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Why did the nightly customer ETL job fail and how do we fix it?",
        help="The user request for the agent to investigate.",
    )
    args = parser.parse_args()

    result = run_agent(args.prompt)
    print(result["final_answer"])


if __name__ == "__main__":
    cli()
