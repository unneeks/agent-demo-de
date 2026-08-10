"""Marketplace resolution -- matching registry agents against engineering roles."""

from engines.composition.resolution import (
    CandidateAssessment,
    RoleResolution,
    assess_candidate,
    assess_conformance,
    resolve_catalog,
    resolve_role,
)

__all__ = [
    "CandidateAssessment",
    "RoleResolution",
    "assess_candidate",
    "assess_conformance",
    "resolve_catalog",
    "resolve_role",
]
