"""`engines.gap_analysis.inference` -- coarse maturity inference, proven
against hand-built pipelines/tests/evaluations. Never returns 5 for either
function; that's asserted explicitly, not just implied by the examples.
"""

from __future__ import annotations

from domain.metamodel.base import EntityRef
from domain.metamodel.enums import EntityType
from engines.gap_analysis import infer_delivery_maturity, infer_technical_maturity

from tests.conftest import make_evaluation, make_pipeline, make_test, ref


class TestInferTechnicalMaturity:
    def test_no_hints_is_zero(self) -> None:
        pipeline = make_pipeline("p1", pipeline_kind="dbt_model")
        assert infer_technical_maturity((), [pipeline], []) == 0

    def test_no_matching_pipeline_is_zero(self) -> None:
        pipeline = make_pipeline("p1", pipeline_kind="script")
        assert infer_technical_maturity(("kafka", "pubsub"), [pipeline], []) == 0

    def test_matching_pipeline_with_no_test_coverage_is_low(self) -> None:
        pipeline = make_pipeline("p1", pipeline_kind="dbt_model")
        assert infer_technical_maturity(("dbt",), [pipeline], []) == 1

    def test_matching_pipeline_with_full_test_coverage_is_higher(self) -> None:
        pipeline = make_pipeline("p1", pipeline_kind="dbt_model")
        test = make_test("t1", covers_refs=[ref(EntityType.PIPELINE, "p1")])
        assert infer_technical_maturity(("dbt",), [pipeline], [test]) == 4

    def test_partial_coverage_across_two_pipelines_is_between(self) -> None:
        covered = make_pipeline("p1", pipeline_kind="dbt_model")
        uncovered = make_pipeline("p2", pipeline_kind="dbt_model")
        test = make_test("t1", covers_refs=[ref(EntityType.PIPELINE, "p1")])
        maturity = infer_technical_maturity(("dbt",), [covered, uncovered], [test])
        assert 1 <= maturity < 4

    def test_never_returns_five(self) -> None:
        pipelines = [make_pipeline(f"p{i}", pipeline_kind="dbt_model") for i in range(5)]
        tests = [make_test(f"t{i}", covers_refs=[ref(EntityType.PIPELINE, f"p{i}")]) for i in range(5)]
        assert infer_technical_maturity(("dbt",), pipelines, tests) <= 4


class TestInferDeliveryMaturity:
    def test_no_governing_contract_is_zero(self) -> None:
        assert infer_delivery_maturity([], []) == 0

    def test_governing_contract_never_evaluated_is_zero(self) -> None:
        assert infer_delivery_maturity(["contract.regression-test"], []) == 0

    def test_passing_evaluation_against_the_governing_contract_scores(self) -> None:
        evaluation = make_evaluation(
            subject_ref=ref(EntityType.DELIVERY_CONTRACT, "contract.regression-test"), passed=True
        )
        maturity = infer_delivery_maturity(["contract.regression-test"], [evaluation])
        assert maturity == 4

    def test_failing_evaluation_against_the_governing_contract_scores_zero(self) -> None:
        evaluation = make_evaluation(
            subject_ref=ref(EntityType.DELIVERY_CONTRACT, "contract.regression-test"), passed=False
        )
        maturity = infer_delivery_maturity(["contract.regression-test"], [evaluation])
        assert maturity == 0

    def test_evaluation_against_a_different_contract_does_not_count(self) -> None:
        evaluation = make_evaluation(
            subject_ref=ref(EntityType.DELIVERY_CONTRACT, "contract.other"), passed=True
        )
        maturity = infer_delivery_maturity(["contract.regression-test"], [evaluation])
        assert maturity == 0

    def test_never_returns_five(self) -> None:
        keys = [f"contract.c{i}" for i in range(5)]
        evaluations = [
            make_evaluation(f"e{i}", subject_ref=ref(EntityType.DELIVERY_CONTRACT, key), passed=True)
            for i, key in enumerate(keys)
        ]
        assert infer_delivery_maturity(keys, evaluations) <= 4
