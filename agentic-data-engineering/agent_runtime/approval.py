"""Gating a tool call against `ToolAction.minimum_approval`.

There is no live human-in-the-loop mechanism anywhere in this codebase --
`ApprovalLevel`/`ActionClass`/`AutomationLevel`/`registry.approval_matrix`/
`registry.required_approval()` are, before this phase, 100% descriptive
data: nothing enforces them live, and there is no pending-approval or
pause-resume concept at all. `AutomationLevelApprovalPolicy` is what
"gated" concretely means here: a synchronous, caller-declared, simulated
authorization check, computed before dispatch and refused (never silently
downgraded) if the caller's declared grant falls short. See
docs/agent-runtime.md and ADR-0017.

Two independently-sourced approval requirements combine via `max()`:

* the automation-level matrix (`registry.required_approval()`,
  `metamodel-registry/risk.yaml`) -- real, existing data, already produces
  SAMPLED_QA for LOW_RISK_WRITE under SUPERVISED_AUTONOMOUS;
* the action's own `minimum_approval` floor (`ToolAction.minimum_approval`)
  -- a per-action override, e.g. github.comment_on_pull_request's
  SINGLE_REVIEWER floor (metamodel-registry/tools.yaml), which holds even
  under automation levels where the matrix alone would say NONE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from domain.metamodel.entities.organization import Tool, ToolAction
from domain.metamodel.enums import APPROVAL_ORDER, ApprovalLevel, AutomationLevel
from domain.metamodel.registry import MetamodelRegistry


@dataclass(frozen=True)
class ApprovalDecision:
    required: ApprovalLevel
    granted: ApprovalLevel
    approved: bool
    reason: str


@runtime_checkable
class ApprovalPolicy(Protocol):
    def decide(self, *, tool: Tool, action: ToolAction, registry: MetamodelRegistry) -> ApprovalDecision:
        ...


class AutomationLevelApprovalPolicy:
    """The one concrete policy this phase ships. Fail-closed by
    construction: `granted` defaults to NONE, so nothing above NONE-required
    executes unless the caller explicitly asserts a higher grant -- the
    same posture `Agent.human_approval_required: bool = True`'s own default
    already takes."""

    def __init__(
        self, *, automation_level: AutomationLevel, granted: ApprovalLevel = ApprovalLevel.NONE
    ) -> None:
        self._automation_level = automation_level
        self._granted = granted

    def decide(self, *, tool: Tool, action: ToolAction, registry: MetamodelRegistry) -> ApprovalDecision:
        matrix_level = registry.required_approval(action.action_class, self._automation_level)
        required = max(matrix_level, action.minimum_approval, key=lambda level: APPROVAL_ORDER[level])
        approved = APPROVAL_ORDER[self._granted] >= APPROVAL_ORDER[required]
        if required is ApprovalLevel.NONE:
            reason = "no approval required"
        elif approved:
            reason = f"granted {self._granted.value} meets required {required.value}"
        else:
            reason = f"granted {self._granted.value} is below required {required.value}"
        return ApprovalDecision(required=required, granted=self._granted, approved=approved, reason=reason)


__all__ = ["ApprovalDecision", "ApprovalPolicy", "AutomationLevelApprovalPolicy"]
