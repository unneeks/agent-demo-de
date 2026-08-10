"""Capability gap analysis -- the "given a project's capability gaps,
resolves which Engineering Roles are needed" half of the original spec's
Composition Engine line ADR-0020 deferred. See docs/gap-analysis.md."""

from engines.gap_analysis.analysis import analyze_capability_gaps
from engines.gap_analysis.chain import tasks_governed_by_delivery_capability
from engines.gap_analysis.inference import infer_delivery_maturity, infer_technical_maturity

__all__ = [
    "analyze_capability_gaps",
    "infer_delivery_maturity",
    "infer_technical_maturity",
    "tasks_governed_by_delivery_capability",
]
