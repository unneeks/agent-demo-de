"""Deterministic, governed context assembly. See ADR-0006."""

from engines.context.assembler import (
    ContextOverflowError,
    DeliveryContextError,
    assemble,
)
from engines.context.budget import (
    DEFAULT_ESTIMATOR,
    FixedTokenEstimator,
    HeuristicTokenEstimator,
    TokenEstimator,
)

__all__ = [
    "DEFAULT_ESTIMATOR",
    "ContextOverflowError",
    "DeliveryContextError",
    "FixedTokenEstimator",
    "HeuristicTokenEstimator",
    "TokenEstimator",
    "assemble",
]
