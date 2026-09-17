"""`LocalToolExecutor` -- real subprocess execution for the actions that
have a genuine developer-machine realization, and honest fallback/failure
for the ones that don't.

`git.read_repository` and `pytest.run_tests` are exercised against real,
throwaway git repos and pytest runs (no network, no fixtures needed --
`git`/`python3` are always available in this environment). `github.*`
actions are only exercised through their failure paths (no `gh` CLI/real
PR available in CI); the request-shape logic those two handlers build is
therefore not independently covered here -- a real repo + PR + `gh` CLI
would be needed for that, which this environment does not have.
"""

from __future__ import annotations

import subprocess
import textwrap
from typing import Any

import pytest

from agent_runtime.errors import AgentRuntimeError, UnknownToolActionError
from agent_runtime.local_tool_executor import LocalToolExecutor, _parse_pytest_summary
from domain.metamodel.enums import ActionClass

from tests.conftest import make_tool


def _make(tool_key: str, action_name: str):
    from domain.metamodel.entities.organization import ToolAction

    tool = make_tool(tool_key, actions=[ToolAction(name=action_name, action_class=ActionClass.READ_ONLY)])
    return tool, tool.action(action_name)


def _init_repo(tmp_path) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True)
    return str(repo)


class TestGitReadRepository:
    def test_reads_branch_head_and_tracked_files(self, tmp_path) -> None:
        repo_path = _init_repo(tmp_path)
        executor = LocalToolExecutor(repo_path=repo_path)
        tool, action = _make("git", "read_repository")

        result = executor.execute(tool=tool, action=action, input={})

        assert result["head_commit"]
        assert {"path": "README.md", "kind": "code"} in result["files"]

    def test_missing_repo_path_fails_clearly(self) -> None:
        executor = LocalToolExecutor()
        tool, action = _make("git", "read_repository")

        with pytest.raises(AgentRuntimeError, match="repo_path"):
            executor.execute(tool=tool, action=action, input={})


class TestPytestRunTests:
    def test_runs_a_passing_test_file_for_real(self, tmp_path) -> None:
        (tmp_path / "test_ok.py").write_text(
            textwrap.dedent(
                """
                def test_one():
                    assert 1 + 1 == 2

                def test_two():
                    assert True
                """
            )
        )
        executor = LocalToolExecutor(repo_path=str(tmp_path))
        tool, action = _make("pytest", "run_tests")

        result = executor.execute(tool=tool, action=action, input={"path": "test_ok.py"})

        assert result["passed"] == 2
        assert result["failed"] == 0

    def test_runs_a_failing_test_file_for_real(self, tmp_path) -> None:
        (tmp_path / "test_bad.py").write_text("def test_fails():\n    assert False\n")
        executor = LocalToolExecutor(repo_path=str(tmp_path))
        tool, action = _make("pytest", "run_tests")

        result = executor.execute(tool=tool, action=action, input={"path": "test_bad.py"})

        assert result["failed"] == 1


class TestParsePytestSummary:
    def test_all_passed(self) -> None:
        assert _parse_pytest_summary("3 passed in 0.10s") == {
            "collected": 3,
            "passed": 3,
            "failed": 0,
            "duration_s": 0.10,
        }

    def test_mixed_pass_and_fail(self) -> None:
        result = _parse_pytest_summary("2 failed, 5 passed in 1.23s")
        assert result["passed"] == 5
        assert result["failed"] == 2

    def test_unparseable_output_degrades_to_zeroes_not_a_crash(self) -> None:
        result = _parse_pytest_summary("no tests ran")
        assert result["passed"] == 0
        assert result["failed"] == 0


class TestGithubActionsRequireTheGhCli:
    def test_missing_gh_binary_fails_clearly(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda name: None)
        executor = LocalToolExecutor(repo="octocat/demo")
        tool, action = _make("github", "read_pull_request")

        with pytest.raises(AgentRuntimeError, match="gh"):
            executor.execute(tool=tool, action=action, input={"number": 1})

    def test_missing_repo_fails_clearly(self) -> None:
        executor = LocalToolExecutor()
        tool, action = _make("github", "read_pull_request")

        with pytest.raises(AgentRuntimeError, match="repo"):
            executor.execute(tool=tool, action=action, input={"number": 1})


class TestFallback:
    def test_unimplemented_action_without_a_fallback_raises(self) -> None:
        executor = LocalToolExecutor()
        tool, action = _make("neo4j", "traverse")

        with pytest.raises(UnknownToolActionError):
            executor.execute(tool=tool, action=action, input={})

    def test_unimplemented_action_delegates_to_a_supplied_fallback(self) -> None:
        class _FakeFallback:
            def execute(self, *, tool: Any, action: Any, input: dict[str, Any]) -> dict[str, Any]:
                return {"delegated": True}

        executor = LocalToolExecutor(fallback=_FakeFallback())
        tool, action = _make("neo4j", "traverse")

        result = executor.execute(tool=tool, action=action, input={})

        assert result == {"delegated": True}

    def test_an_implemented_action_never_reaches_the_fallback(self, tmp_path) -> None:
        class _ExplodingFallback:
            def execute(self, *, tool: Any, action: Any, input: dict[str, Any]) -> dict[str, Any]:
                raise AssertionError("fallback should not be consulted for an implemented action")

        repo_path = _init_repo(tmp_path)
        executor = LocalToolExecutor(repo_path=repo_path, fallback=_ExplodingFallback())
        tool, action = _make("git", "read_repository")

        result = executor.execute(tool=tool, action=action, input={})

        assert result["head_commit"]
