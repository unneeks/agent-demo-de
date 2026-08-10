"""Token estimation, behind a port.

Counting tokens exactly requires a tokenizer, which is model-specific and would
drag a vendor dependency into the foundation. So estimation is a port with a
deterministic default, and a real tokenizer can be dropped in later without
touching the assembler.

The default must be *deterministic and monotonic*, not accurate: the assembler's
job is to enforce a budget reproducibly, and a bundle hash that changed because
a tokenizer was upgraded would be worse than one from a crude but stable
estimate.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

#: Rough average characters per token for English prose plus code. Deliberately
#: conservative -- overestimating costs budget, underestimating overflows it.
_CHARS_PER_TOKEN = 4.0

_WORD_RE = re.compile(r"\w+|[^\w\s]")


@runtime_checkable
class TokenEstimator(Protocol):
    """Estimates the token cost of a piece of text."""

    def estimate(self, text: str) -> int: ...


class HeuristicTokenEstimator:
    """Character- and word-based estimate. No model dependency.

    Takes the larger of the two, so dense code -- few spaces, many symbols -- is
    not systematically underestimated the way a whitespace split would be.
    """

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        by_chars = len(text) / _CHARS_PER_TOKEN
        by_words = len(_WORD_RE.findall(text))
        return max(1, int(max(by_chars, by_words)))


class FixedTokenEstimator:
    """Returns a constant per item. Used by tests asserting budget arithmetic."""

    def __init__(self, tokens_per_item: int = 100) -> None:
        self._tokens = tokens_per_item

    def estimate(self, text: str) -> int:  # noqa: ARG002 - constant by design
        return self._tokens


DEFAULT_ESTIMATOR: TokenEstimator = HeuristicTokenEstimator()
