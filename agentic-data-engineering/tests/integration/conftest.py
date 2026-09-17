"""Shared gate for the worked-example live tests.

`agentic-ai-ollama-demo/` is a sibling checkout, not part of this repo --
absent in any environment that only cloned `agentic-data-engineering/` on its
own. Both live tests need it (it's the same real project the golden fixtures
were recorded from), so the path-exists check lives here once rather than
duplicated per test, mirroring `tests/contract/conftest.py`'s TCP-probe-skip
precedent for "the thing this test needs isn't available here."
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SIBLING_PROJECT = REPO_ROOT.parent / "agentic-ai-ollama-demo"
GOLDEN_DIR = REPO_ROOT / "tests" / "fixtures" / "discovery" / "golden"


@pytest.fixture
def sibling_project() -> Path:
    if not SIBLING_PROJECT.is_dir():
        pytest.skip("agentic-ai-ollama-demo/ sibling project not present")
    return SIBLING_PROJECT
