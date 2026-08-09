"""`AutomationLevelApprovalPolicy` against the real `risk.yaml` matrix, plus
the worked `github.comment_on_pull_request` `minimum_approval` floor that
makes `ToolAction.minimum_approval` load-bearing under every automation
level, not just SUPERVISED_AUTONOMOUS (see docs/agent-runtime.md and
ADR-0017)."""

from __future__ import annotations

import pytest

from agent_runtime.approval import AutomationLevelApprovalPolicy
from domain.metamodel.enums import ApprovalLevel, AutomationLevel


class TestMatrixOnly:
    """github.read_pull_request is READ_ONLY with minimum_approval=NONE --
    the matrix alone governs it."""

    @pytest.mark.parametrize(
        ("automation_level", "expected"),
        [
            (AutomationLevel.ASSISTED, ApprovalLevel.NONE),
            (AutomationLevel.SUPERVISED_AUTONOMOUS, ApprovalLevel.NONE),
            (AutomationLevel.AUTONOMOUS, ApprovalLevel.NONE),
        ],
    )
    def test_read_only_never_requires_approval(self, registry, automation_level, expected) -> None:
        tool = registry.tools["github"]
        action = tool.action("read_pull_request")
        policy = AutomationLevelApprovalPolicy(automation_level=automation_level)
        decision = policy.decide(tool=tool, action=action, registry=registry)
        assert decision.required == expected


class TestMinimumApprovalFloor:
    """github.comment_on_pull_request carries minimum_approval=SINGLE_REVIEWER
    -- it must win over the matrix under every automation level, including
    ASSISTED and AUTONOMOUS where the matrix alone says NONE for
    LOW_RISK_WRITE."""

    @pytest.mark.parametrize(
        "automation_level",
        [AutomationLevel.ASSISTED, AutomationLevel.SUPERVISED_AUTONOMOUS, AutomationLevel.AUTONOMOUS],
    )
    def test_floor_wins_over_the_matrix(self, registry, automation_level) -> None:
        tool = registry.tools["github"]
        action = tool.action("comment_on_pull_request")
        assert action.minimum_approval is ApprovalLevel.SINGLE_REVIEWER

        policy = AutomationLevelApprovalPolicy(automation_level=automation_level)
        decision = policy.decide(tool=tool, action=action, registry=registry)
        assert decision.required == ApprovalLevel.SINGLE_REVIEWER

    def test_matrix_can_still_exceed_the_floor(self, registry) -> None:
        """pytest.run_tests has minimum_approval=NONE (the default), so under
        SUPERVISED_AUTONOMOUS the matrix's SAMPLED_QA for LOW_RISK_WRITE
        wins -- max() genuinely combines both sources, not just the floor."""
        tool = registry.tools["pytest"]
        action = tool.action("run_tests")
        assert action.minimum_approval is ApprovalLevel.NONE

        policy = AutomationLevelApprovalPolicy(automation_level=AutomationLevel.SUPERVISED_AUTONOMOUS)
        decision = policy.decide(tool=tool, action=action, registry=registry)
        assert decision.required == ApprovalLevel.SAMPLED_QA


class TestGrantComparison:
    def test_sufficient_grant_is_approved(self, registry) -> None:
        tool = registry.tools["github"]
        action = tool.action("comment_on_pull_request")
        policy = AutomationLevelApprovalPolicy(
            automation_level=AutomationLevel.ASSISTED, granted=ApprovalLevel.SINGLE_REVIEWER
        )
        decision = policy.decide(tool=tool, action=action, registry=registry)
        assert decision.approved is True

    def test_insufficient_grant_is_denied(self, registry) -> None:
        tool = registry.tools["github"]
        action = tool.action("comment_on_pull_request")
        policy = AutomationLevelApprovalPolicy(automation_level=AutomationLevel.ASSISTED)
        decision = policy.decide(tool=tool, action=action, registry=registry)
        assert decision.approved is False
        assert decision.granted is ApprovalLevel.NONE

    def test_default_grant_is_none_fail_closed(self, registry) -> None:
        tool = registry.tools["pytest"]
        action = tool.action("run_tests")
        policy = AutomationLevelApprovalPolicy(automation_level=AutomationLevel.SUPERVISED_AUTONOMOUS)
        decision = policy.decide(tool=tool, action=action, registry=registry)
        assert decision.approved is False
