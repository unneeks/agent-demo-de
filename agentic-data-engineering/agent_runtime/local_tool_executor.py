"""`LocalToolExecutor` -- the first real (non-simulated) `ToolExecutor`,
running actions on the same machine the web app itself runs on. This is
"the developer machine" the AgentCore harness's `inlineFunction` tool
calls are returned to for execution (see `agent_runtime/agentcore_client.py`).

Deliberately partial, and honest about it rather than faking coverage:
only actions with a genuine, generic "run this on any developer's machine"
realization are implemented for real here --
`git.read_repository`/`pytest.run_tests` via subprocess,
`github.read_pull_request`/`github.comment_on_pull_request` via the `gh`
CLI (the same binary `discovery.extraction.copilot_cli_client` and
`scripts/onboard_project.py` already standardize on -- one convention for
"how this codebase shells out to GitHub," not a second one). The
remaining catalog actions (`neo4j.traverse`, `bigquery.profile_query`,
`modeling-tool.*`, `metadata-platform.*`, `github.copilot_code_review`)
have no such generic realization -- they need a live database/warehouse
connection or a hosted review feature this executor cannot responsibly
fake -- so they fall through to a caller-supplied `fallback` `ToolExecutor`
(e.g. `SimulatedToolExecutor`) when one is given, and raise
`UnknownToolActionError` otherwise, exactly `SimulatedToolExecutor`'s own
"never fabricate a plausible-looking response for a call nobody defined"
discipline.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

from domain.metamodel.entities.organization import Tool, ToolAction

from agent_runtime.errors import AgentRuntimeError, UnknownToolActionError

#: Mirrors discovery.extraction.copilot_cli_client._CANDIDATE_BINARIES --
#: one place decides "the GitHub CLI" means `gh`, reused rather than
#: re-picked here.
_GH_BINARY = "gh"

#: pytest's summary line lists whichever counts are nonzero, in varying
#: combinations and order ("3 passed in 0.10s", "1 failed in 0.02s",
#: "2 failed, 5 passed in 1.23s", ...) -- each count is matched
#: independently rather than with one combined pattern, so any subset or
#: order still parses.
_COUNT_PATTERN = re.compile(r"(?P<count>\d+) (?P<kind>passed|failed|skipped)")
_DURATION_PATTERN = re.compile(r"in (?P<duration>[\d.]+)s")


class LocalToolExecutor:
    """`repo_path` scopes `git`/`pytest` actions; `repo` (``"owner/name"``)
    scopes `github` actions via the `gh` CLI. Both are required only if the
    corresponding tool is actually used -- a workflow whose agents never
    call `github__*` never needs a `repo`."""

    def __init__(
        self,
        *,
        repo_path: str | None = None,
        repo: str | None = None,
        fallback: Any | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self._repo_path = repo_path
        self._repo = repo
        self._fallback = fallback
        self._timeout_seconds = timeout_seconds

    def execute(self, *, tool: Tool, action: ToolAction, input: dict[str, Any]) -> dict[str, Any]:
        key = (tool.tool_key, action.name)
        handler = _HANDLERS.get(key)
        if handler is not None:
            return handler(self, input)
        if self._fallback is not None:
            return self._fallback.execute(tool=tool, action=action, input=input)
        raise UnknownToolActionError(f"no local (real) backend for {key!r}, and no fallback executor given")

    # -- git -----------------------------------------------------------

    def _git_read_repository(self, _input: dict[str, Any]) -> dict[str, Any]:
        repo_path = self._require_repo_path()
        branch = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
        head_commit = self._run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_path)
        tracked = self._run(["git", "ls-files"], cwd=repo_path)
        files = [{"path": path, "kind": "code"} for path in tracked.splitlines() if path]
        return {"branch": branch, "head_commit": head_commit, "files": files}

    # -- pytest ----------------------------------------------------------

    def _pytest_run_tests(self, input: dict[str, Any]) -> dict[str, Any]:
        repo_path = self._require_repo_path()
        target = input.get("path", ".")
        result = subprocess.run(
            ["python3", "-m", "pytest", "-q", target],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
        )
        return _parse_pytest_summary(result.stdout + result.stderr)

    # -- github (via the `gh` CLI) ---------------------------------------

    def _github_read_pull_request(self, input: dict[str, Any]) -> dict[str, Any]:
        repo = self._require_repo()
        number = str(input["number"])
        output = self._run(
            [
                _GH_BINARY,
                "pr",
                "view",
                number,
                "--repo",
                repo,
                "--json",
                "number,title,state,additions,deletions,changedFiles",
            ]
        )
        import json

        payload = json.loads(output)
        additions, deletions, changed = (
            payload.get("additions", 0),
            payload.get("deletions", 0),
            payload.get("changedFiles", 0),
        )
        return {
            "number": payload.get("number"),
            "title": payload.get("title"),
            "state": str(payload.get("state", "")).lower(),
            "diff_summary": f"{changed} file(s) changed, {additions} insertion(s)(+), {deletions} deletion(s)(-)",
        }

    def _github_comment_on_pull_request(self, input: dict[str, Any]) -> dict[str, Any]:
        repo = self._require_repo()
        number = str(input["number"])
        body = input.get("body", "")
        self._run([_GH_BINARY, "pr", "comment", number, "--repo", repo, "--body", body])
        return {"comment_id": f"{repo}#{number}", "url": f"https://github.com/{repo}/pull/{number}"}

    # -- helpers -----------------------------------------------------------

    def _require_repo_path(self) -> str:
        if not self._repo_path:
            raise AgentRuntimeError("LocalToolExecutor needs repo_path= to run a git/pytest action")
        return self._repo_path

    def _require_repo(self) -> str:
        if not self._repo:
            raise AgentRuntimeError("LocalToolExecutor needs repo= (owner/name) to run a github action")
        if shutil.which(_GH_BINARY) is None:
            raise AgentRuntimeError(f"the '{_GH_BINARY}' CLI is not on PATH -- required for github actions")
        return self._repo

    def _run(self, argv: list[str], *, cwd: str | None = None) -> str:
        try:
            result = subprocess.run(
                argv, cwd=cwd, capture_output=True, text=True, timeout=self._timeout_seconds, check=True
            )
        except FileNotFoundError as exc:
            raise AgentRuntimeError(f"command not found: {argv[0]}") from exc
        except subprocess.CalledProcessError as exc:
            raise AgentRuntimeError(f"{' '.join(argv)} failed: {exc.stderr.strip()}") from exc
        return result.stdout.strip()


def _parse_pytest_summary(output: str) -> dict[str, Any]:
    # Only the final summary line's counts, not any earlier mention of
    # "N passed" inside a traceback -- pytest always prints its own
    # summary last, so scanning the last non-blank line is enough.
    summary_line = next((line for line in reversed(output.splitlines()) if line.strip()), "")
    counts = {kind: int(count) for count, kind in _COUNT_PATTERN.findall(summary_line)}
    duration_match = _DURATION_PATTERN.search(summary_line)
    if not counts and duration_match is None:
        return {"collected": 0, "passed": 0, "failed": 0, "duration_s": 0.0, "raw_output": output[-2000:]}
    passed, failed, skipped = counts.get("passed", 0), counts.get("failed", 0), counts.get("skipped", 0)
    return {
        "collected": passed + failed + skipped,
        "passed": passed,
        "failed": failed,
        "duration_s": float(duration_match.group("duration")) if duration_match else 0.0,
    }


_HANDLERS: dict[tuple[str, str], Any] = {
    ("git", "read_repository"): LocalToolExecutor._git_read_repository,
    ("pytest", "run_tests"): LocalToolExecutor._pytest_run_tests,
    ("github", "read_pull_request"): LocalToolExecutor._github_read_pull_request,
    ("github", "comment_on_pull_request"): LocalToolExecutor._github_comment_on_pull_request,
}


__all__ = ["LocalToolExecutor"]
