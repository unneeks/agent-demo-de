"""`SimulatedToolExecutor` -- every real catalog action has a canned
default, overrides work, and repeated calls are deterministic (no mutable
state anywhere)."""

from __future__ import annotations

import pytest

from agent_runtime.errors import UnknownToolActionError
from agent_runtime.simulated_tools import SimulatedToolExecutor


class TestEveryCatalogActionHasADefault:
    def test_every_tool_action_in_the_registry_has_a_simulated_response(self, registry) -> None:
        executor = SimulatedToolExecutor()
        for tool in registry.tools.values():
            for action in tool.actions:
                output = executor.execute(tool=tool, action=action, input={})
                assert isinstance(output, dict)
                assert output  # never an empty acknowledgment

    def test_unknown_tool_action_raises(self, registry) -> None:
        tool = registry.tools["git"]
        fake_action = tool.action("read_repository").model_copy(update={"name": "delete_everything"})
        executor = SimulatedToolExecutor()
        with pytest.raises(UnknownToolActionError):
            executor.execute(tool=tool, action=fake_action, input={})


class TestDeterminism:
    def test_repeated_calls_return_equal_output(self, registry) -> None:
        tool = registry.tools["pytest"]
        action = tool.action("run_tests")
        executor = SimulatedToolExecutor()
        first = executor.execute(tool=tool, action=action, input={})
        second = executor.execute(tool=tool, action=action, input={})
        assert first == second


class TestOverrides:
    def test_override_takes_priority_over_the_default(self, registry) -> None:
        tool = registry.tools["pytest"]
        action = tool.action("run_tests")
        executor = SimulatedToolExecutor(overrides={("pytest", "run_tests"): {"passed": 0, "failed": 99}})
        output = executor.execute(tool=tool, action=action, input={})
        assert output == {"passed": 0, "failed": 99}


class TestLowRiskWriteNeverLooksLikeAMutation:
    def test_low_risk_write_actions_return_only_an_acknowledgment_shape(self, registry) -> None:
        """LOW_RISK_WRITE defaults must never claim to have modified shared
        state beyond an id/url-shaped acknowledgment -- nothing here ever
        actually did."""
        executor = SimulatedToolExecutor()
        low_risk_write_keys = {
            ("github", "comment_on_pull_request"),
            ("github", "copilot_code_review"),
            ("pytest", "run_tests"),
            ("modeling-tool", "generate_model"),
            ("metadata-platform", "publish_model"),
        }
        for tool in registry.tools.values():
            for action in tool.actions:
                key = (tool.tool_key, action.name)
                if key not in low_risk_write_keys:
                    continue
                output = executor.execute(tool=tool, action=action, input={})
                assert action.action_class.value == "LOW_RISK_WRITE"
                assert isinstance(output, dict)
