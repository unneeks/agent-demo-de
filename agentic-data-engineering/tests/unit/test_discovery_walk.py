"""Deterministic file discovery and classification.

Mechanical enumeration only -- these tests never touch extraction, just
"what did the walk find and how did it classify it."
"""

from __future__ import annotations

from pathlib import Path

from discovery.walk import (
    CI_WORKFLOW,
    COMPOSE,
    CSV,
    DOCKERFILE,
    MARKDOWN,
    SQL,
    TERRAFORM,
    YAML_CONFIG,
    classify_file,
    discover_candidate_files,
)


class TestClassifyFile:
    def test_dockerfile_by_name(self) -> None:
        assert classify_file(Path("Dockerfile")) == DOCKERFILE

    def test_compose_by_name(self) -> None:
        assert classify_file(Path("docker-compose.yml")) == COMPOSE
        assert classify_file(Path("compose.yaml")) == COMPOSE

    def test_ci_workflow_by_path(self) -> None:
        assert classify_file(Path(".github/workflows/ci.yml")) == CI_WORKFLOW

    def test_a_yaml_file_outside_workflows_is_not_ci(self) -> None:
        assert classify_file(Path("config/settings.yml")) is None

    def test_terraform_by_extension(self) -> None:
        assert classify_file(Path("infra/main.tf")) == TERRAFORM

    def test_sql_by_extension(self) -> None:
        assert classify_file(Path("models/stg_customers.sql")) == SQL

    def test_csv_by_extension(self) -> None:
        assert classify_file(Path("seeds/customers.csv")) == CSV

    def test_markdown_by_extension(self) -> None:
        assert classify_file(Path("README.md")) == MARKDOWN

    def test_dbt_project_yml_by_name(self) -> None:
        assert classify_file(Path("dbt_project.yml")) == YAML_CONFIG
        assert classify_file(Path("profiles.yml")) == YAML_CONFIG

    def test_unrecognized_file_is_not_a_candidate(self) -> None:
        assert classify_file(Path("agent/main.py")) is None
        assert classify_file(Path("requirements.txt")) is None


class TestDiscoverCandidateFiles:
    def test_walks_a_directory_tree(self, tmp_path: Path) -> None:
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "a.sql").write_text("select 1")
        (tmp_path / "README.md").write_text("hello")
        (tmp_path / "notes.txt").write_text("ignored")

        candidates = discover_candidate_files(tmp_path)
        found = {(c.path.as_posix(), c.source_kind) for c in candidates}
        assert found == {("models/a.sql", SQL), ("README.md", MARKDOWN)}

    def test_denylisted_directories_are_pruned(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config.sql").write_text("select 1")
        (tmp_path / "dbt_packages").mkdir()
        (tmp_path / "dbt_packages" / "vendored.sql").write_text("select 1")
        (tmp_path / "real.sql").write_text("select 1")

        candidates = discover_candidate_files(tmp_path)
        assert [c.path.as_posix() for c in candidates] == ["real.sql"]

    def test_extra_exclude_dirs_are_respected(self, tmp_path: Path) -> None:
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "third_party.sql").write_text("select 1")
        (tmp_path / "mine.sql").write_text("select 1")

        candidates = discover_candidate_files(tmp_path, extra_exclude_dirs=frozenset({"vendor"}))
        assert [c.path.as_posix() for c in candidates] == ["mine.sql"]

    def test_absolute_path_is_the_real_file(self, tmp_path: Path) -> None:
        (tmp_path / "a.sql").write_text("select 1")
        [candidate] = discover_candidate_files(tmp_path)
        assert candidate.absolute_path == tmp_path / "a.sql"
        assert candidate.absolute_path.read_text() == "select 1"

    def test_results_are_sorted(self, tmp_path: Path) -> None:
        (tmp_path / "z.sql").write_text("select 1")
        (tmp_path / "a.sql").write_text("select 1")
        candidates = discover_candidate_files(tmp_path)
        assert [c.path.as_posix() for c in candidates] == ["a.sql", "z.sql"]
