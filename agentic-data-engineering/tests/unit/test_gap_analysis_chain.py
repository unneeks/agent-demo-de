"""`engines.gap_analysis.chain.tasks_governed_by_delivery_capability` --
the reverse of `orchestrator/staffing.py::engineering_roles_for_obligation()`'s
forward walk, proven against the real worked registry so it stays
consistent with that forward walk's own fixtures.
"""

from __future__ import annotations

from engines.gap_analysis import tasks_governed_by_delivery_capability


class TestTasksGovernedByDeliveryCapability:
    def test_regression_assurance_governs_the_regression_test_task(
        self, registry, delivery_model
    ) -> None:
        """regression-assurance.realized_by_roles == [regression-engineer]
        (metamodel-registry/delivery_capabilities.yaml); regression-engineer
        fulfils resp.regression-proof; test-lead is accountable for
        resp.regression-proof and for task.regression-test -- the same
        chain `orchestrator/staffing.py`'s own worked example walks forward."""
        tasks = tasks_governed_by_delivery_capability("regression-assurance", registry, delivery_model)
        assert "task.regression-test" in tasks

    def test_unknown_delivery_capability_returns_empty(self, registry, delivery_model) -> None:
        assert tasks_governed_by_delivery_capability("no-such-capability", registry, delivery_model) == []

    def test_result_has_no_duplicate_tasks(self, registry, delivery_model) -> None:
        tasks = tasks_governed_by_delivery_capability("regression-assurance", registry, delivery_model)
        assert len(tasks) == len(set(tasks))
