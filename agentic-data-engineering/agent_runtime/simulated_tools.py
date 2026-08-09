"""`SimulatedToolExecutor` -- the only `ToolExecutor` this phase ships.

Deterministic, in-memory, no I/O of any kind: every response is either a
caller-supplied override or one fixed default per real catalog action
(`metamodel-registry/tools.yaml`). LOW_RISK_WRITE defaults return only an
id/url-shaped acknowledgment -- never anything that looks like it mutated
shared state, because nothing here ever does. Unknown (tool_key,
action_name) pairs raise `UnknownToolActionError` rather than fabricating a
plausible-looking response for a call nobody defined.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domain.metamodel.entities.organization import Tool, ToolAction

from agent_runtime.errors import UnknownToolActionError

ResponseBuilder = Callable[[dict[str, Any]], dict[str, Any]]


def _git_read_repository(_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "branch": "main",
        "head_commit": "a1b2c3d",
        "files": [
            {"path": "models/stg_customers.sql", "kind": "code"},
            {"path": "models/mart_customer_360.sql", "kind": "code"},
        ],
    }


def _github_read_pull_request(_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": 42,
        "title": "Add customer address column",
        "state": "open",
        "diff_summary": "1 file changed, 12 insertions(+), 2 deletions(-)",
    }


def _github_comment_on_pull_request(_input: dict[str, Any]) -> dict[str, Any]:
    return {"comment_id": "c-1", "url": "https://example.invalid/pull/42#comment-1"}


def _github_copilot_code_review(_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_id": "r-1",
        "findings": [{"severity": "medium", "summary": "Consider adding a null check."}],
    }


def _pytest_run_tests(_input: dict[str, Any]) -> dict[str, Any]:
    return {"collected": 12, "passed": 11, "failed": 1, "duration_s": 4.2}


def _neo4j_traverse(_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "nodes": [{"id": "Pipeline:stg_customers"}, {"id": "Pipeline:mart_customer_360"}],
        "edges": [{"source": "Pipeline:stg_customers", "type": "DEPENDS_ON", "target": "Pipeline:mart_customer_360"}],
    }


def _bigquery_profile_query(_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_count": 10432,
        "columns": [{"name": "customer_id", "null_rate": 0.0, "distinct_count": 10432}],
    }


def _modeling_tool_validate_model(_input: dict[str, Any]) -> dict[str, Any]:
    return {"valid": True, "violations": []}


def _modeling_tool_generate_model(_input: dict[str, Any]) -> dict[str, Any]:
    return {"model_id": "m-1", "entities": ["Customer", "Address"], "diagram_ref": "model://m-1"}


def _metadata_platform_lookup(_input: dict[str, Any]) -> dict[str, Any]:
    return {"asset": "customer_360", "owner": "data-platform-team", "classification": "internal"}


def _metadata_platform_publish_model(_input: dict[str, Any]) -> dict[str, Any]:
    return {"published_version": "1.0.0", "catalog_url": "metadata-platform://models/m-1"}


_DEFAULT_RESPONSES: dict[tuple[str, str], ResponseBuilder] = {
    ("git", "read_repository"): _git_read_repository,
    ("github", "read_pull_request"): _github_read_pull_request,
    ("github", "comment_on_pull_request"): _github_comment_on_pull_request,
    ("github", "copilot_code_review"): _github_copilot_code_review,
    ("pytest", "run_tests"): _pytest_run_tests,
    ("neo4j", "traverse"): _neo4j_traverse,
    ("bigquery", "profile_query"): _bigquery_profile_query,
    ("modeling-tool", "validate_model"): _modeling_tool_validate_model,
    ("modeling-tool", "generate_model"): _modeling_tool_generate_model,
    ("metadata-platform", "lookup"): _metadata_platform_lookup,
    ("metadata-platform", "publish_model"): _metadata_platform_publish_model,
}

#: Actions whose canned output is evidence-worthy, and what evidence_kind it
#: maps to. Everything else that runs still produces "tool_output" evidence
#: -- see agent_runtime/loop.py.
EVIDENCE_KIND_BY_ACTION: dict[tuple[str, str], str] = {
    ("pytest", "run_tests"): "test_result",
    ("github", "copilot_code_review"): "review_record",
}


class SimulatedToolExecutor:
    """Deterministic, no mutable state. Callers may supply `overrides` keyed
    by (tool_key, action_name) for tests or worked examples."""

    def __init__(self, *, overrides: dict[tuple[str, str], dict[str, Any]] | None = None) -> None:
        self._overrides = dict(overrides or {})

    def execute(self, *, tool: Tool, action: ToolAction, input: dict[str, Any]) -> dict[str, Any]:
        key = (tool.tool_key, action.name)
        if key in self._overrides:
            return self._overrides[key]
        builder = _DEFAULT_RESPONSES.get(key)
        if builder is None:
            raise UnknownToolActionError(f"no simulated backend for {key!r}")
        return builder(input)


__all__ = ["EVIDENCE_KIND_BY_ACTION", "SimulatedToolExecutor"]
