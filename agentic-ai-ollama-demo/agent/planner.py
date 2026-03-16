from __future__ import annotations

import os
from typing import Iterable

import requests


DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
DEFAULT_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class OllamaClient:
    """Tiny wrapper around the Ollama generate API."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL, timeout: int = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        if system_prompt:
            payload["system"] = system_prompt

        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        return body.get("response", "").strip()


def build_goal_summary(client: OllamaClient, user_request: str) -> str:
    prompt = f"""
You are an AI systems engineer helping with a failing data pipeline.
Turn the request into a crisp goal statement for an agent workflow.

User request:
{user_request}
""".strip()
    return client.generate(prompt, system_prompt="Respond in 2-4 concise sentences.")


def build_plan(client: OllamaClient, goal: str, available_tools: Iterable[str]) -> list[str]:
    tool_text = ", ".join(available_tools)
    prompt = f"""
Goal:
{goal}

Available tools:
{tool_text}

Create a short execution plan for a local agent investigating a failed nightly ETL pipeline.
Use one step per line. Mention when to analyze logs, inspect metadata, assess system health,
generate a fix, and verify the rerun.
""".strip()
    raw_plan = client.generate(prompt, system_prompt="Return 5-7 plain text lines with no numbering.")
    return [line.strip("- ").strip() for line in raw_plan.splitlines() if line.strip()]
