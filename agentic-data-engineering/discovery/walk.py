"""Deterministic file discovery and classification.

Walks a directory tree and classifies each file by name/extension/path into a
``source_kind`` -- mechanical enumeration, never interpretation. This module
never opens a file and reasons about its content; it produces only
``CandidateFile(path, source_kind)``, never a fact. Everything downstream of
"here is a file's raw bytes" belongs to ``discovery.extraction``, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: Directories this phase never walks into. An implementation exclusion
#: list, not registry vocabulary (ADR-0002) -- overridable per call via
#: ``extra_exclude_dirs``, not editable YAML data.
DEFAULT_EXCLUDE_DIRS = frozenset(
    {".git", "__pycache__", "target", "dbt_packages", "node_modules", ".venv"}
)

# Source kinds this phase can classify. There is no "other" bucket: a source
# kind is what drives which extraction schema `extraction.prompts` offers,
# and there is no schema to offer for a kind nothing recognizes -- a file
# that doesn't match one of these is simply not a discovery candidate.
SQL = "sql"
CSV = "csv"
DOCKERFILE = "dockerfile"
COMPOSE = "compose"
CI_WORKFLOW = "ci_workflow"
TERRAFORM = "terraform"
MARKDOWN = "markdown"
YAML_CONFIG = "yaml_config"

#: Every technical-file source kind -- everything except MARKDOWN, which is
#: the one delivery-document kind and is handled in its own orchestration pass.
TECHNICAL_SOURCE_KINDS = frozenset(
    {SQL, CSV, DOCKERFILE, COMPOSE, CI_WORKFLOW, TERRAFORM, YAML_CONFIG}
)
DELIVERY_SOURCE_KINDS = frozenset({MARKDOWN})


@dataclass(frozen=True)
class CandidateFile:
    """One file the walk found and classified, ready for extraction."""

    #: Relative to the walked root -- what becomes `source_document`.
    path: Path
    absolute_path: Path
    source_kind: str


def classify_file(relative_path: Path) -> str | None:
    """Classify one file by its name/extension/path. ``None`` means "not a
    discovery candidate" -- there is nothing here to hand to extraction."""
    name = relative_path.name
    posix = relative_path.as_posix()

    if name == "Dockerfile" or name.endswith(".dockerfile"):
        return DOCKERFILE
    if name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        return COMPOSE
    if ".github/workflows/" in posix and relative_path.suffix in (".yml", ".yaml"):
        return CI_WORKFLOW
    if relative_path.suffix == ".tf":
        return TERRAFORM
    if relative_path.suffix == ".sql":
        return SQL
    if relative_path.suffix == ".csv":
        return CSV
    if relative_path.suffix == ".md":
        return MARKDOWN
    if name in ("dbt_project.yml", "profiles.yml"):
        return YAML_CONFIG
    return None


def discover_candidate_files(
    root: Path,
    *,
    extra_exclude_dirs: frozenset[str] = frozenset(),
) -> list[CandidateFile]:
    """Walk ``root``, classify every file, and return the candidates found.

    Deterministic and content-blind: it never opens a file. Directories in
    the denylist (plus any caller-supplied ``extra_exclude_dirs``) are
    pruned from the walk entirely. Sorted by relative path so a run's file
    order -- and therefore prompt-building order -- is stable and reproducible.
    """
    exclude_dirs = DEFAULT_EXCLUDE_DIRS | extra_exclude_dirs
    candidates: list[CandidateFile] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in exclude_dirs for part in relative.parts):
            continue
        kind = classify_file(relative)
        if kind is not None:
            candidates.append(CandidateFile(path=relative, absolute_path=path, source_kind=kind))

    return candidates
