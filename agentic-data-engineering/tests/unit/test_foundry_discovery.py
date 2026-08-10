"""``engines/foundry/discovery.py``: deterministic, crude-by-design grouping
of EngineeringObservations into EngineeringPatterns. Pure, no I/O, no LLM.
"""

from __future__ import annotations

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.foundry import EngineeringObservation
from domain.metamodel.enums import EntityType, ProvenanceState
from engines.foundry.discovery import discover_patterns

PROJECT_REF = EntityRef(type=EntityType.PROJECT, id="demo")


def _observation(
    obs_id: str,
    *,
    source_type: str = "pipeline",
    activity: str = "dbt_model",
    technology: str | None = "airflow",
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> EngineeringObservation:
    return EngineeringObservation(
        id=obs_id,
        name=obs_id,
        entity_type=EntityType.ENGINEERING_OBSERVATION,
        project_ref=PROJECT_REF,
        source_ref=EntityRef(type=EntityType.PIPELINE, id=obs_id),
        source_type=source_type,
        activity=activity,
        inputs=inputs if inputs is not None else ["raw_orders"],
        outputs=outputs if outputs is not None else ["stg_orders"],
        technology=technology,
        provenance=ProvenanceState.OBSERVED,
        confidence=1.0,
        discovered_by="test",
    )


class TestGroupingAndFrequencyThreshold:
    def test_a_group_below_min_frequency_produces_no_pattern(self) -> None:
        observations = [_observation("o1")]
        patterns = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        assert patterns == []

    def test_a_group_at_or_above_min_frequency_produces_one_pattern(self) -> None:
        observations = [_observation("o1"), _observation("o2"), _observation("o3")]
        [pattern] = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        assert pattern.frequency == 3
        assert len(pattern.observation_refs) == 3

    def test_different_activities_never_group(self) -> None:
        observations = [
            _observation("o1", activity="dbt_model"),
            _observation("o2", activity="airflow_dag"),
        ]
        patterns = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        assert patterns == []

    def test_same_activity_different_technology_never_groups_together(self) -> None:
        observations = [
            _observation("o1", technology="airflow"),
            _observation("o2", technology="dagster"),
            _observation("o3", technology="airflow"),
            _observation("o4", technology="dagster"),
        ]
        patterns = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        assert len(patterns) == 2
        assert {p.common_technology for p in patterns} == {"airflow", "dagster"}


class TestNoSemanticClustering:
    def test_differently_labeled_but_semantically_identical_activities_do_not_group(self) -> None:
        """The stated, crude-by-design limitation: grouping is exact-match
        on activity, not semantic similarity. 'dbt_model' and 'dbt-model'
        describe the same real-world thing to a human, but are two distinct
        groups here -- deliberately, since this step has no LLM in it.
        """
        observations = [
            _observation("o1", activity="dbt_model"),
            _observation("o2", activity="dbt_model"),
            _observation("o3", activity="dbt-model"),
            _observation("o4", activity="dbt-model"),
        ]
        patterns = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        assert len(patterns) == 2
        assert {p.common_activity for p in patterns} == {"dbt_model", "dbt-model"}


class TestSimilarityAndCommonFields:
    def test_identical_io_across_the_group_yields_similarity_one(self) -> None:
        observations = [_observation("o1"), _observation("o2")]
        [pattern] = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        assert pattern.similarity_score == 1.0
        assert pattern.confidence == 1.0
        assert pattern.common_inputs == ["raw_orders"]
        assert pattern.common_outputs == ["stg_orders"]
        assert pattern.known_variations == []

    def test_partial_io_overlap_lowers_similarity_and_notes_variation(self) -> None:
        observations = [
            _observation("o1", inputs=["raw_orders", "raw_customers"], outputs=["stg_orders"]),
            _observation("o2", inputs=["raw_orders"], outputs=["stg_orders"]),
        ]
        [pattern] = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        assert 0.0 < pattern.similarity_score < 1.0
        assert pattern.common_inputs == ["raw_orders"]
        assert any("raw_customers" in note for note in pattern.known_variations)

    def test_pattern_key_is_deterministic(self) -> None:
        observations = [_observation("o1"), _observation("o2")]
        [first] = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        [second] = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        assert first.pattern_key == second.pattern_key
        assert first.pattern_key == "pattern.pipeline_shape.dbt_model.airflow"

    def test_pattern_key_handles_no_technology(self) -> None:
        observations = [
            _observation("o1", technology=None),
            _observation("o2", technology=None),
        ]
        [pattern] = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        assert pattern.pattern_key == "pattern.pipeline_shape.dbt_model.none"

    def test_pattern_is_marked_not_yet_synthesized(self) -> None:
        observations = [_observation("o1"), _observation("o2")]
        [pattern] = discover_patterns(observations, project_ref=PROJECT_REF, min_frequency=2)
        assert pattern.synthesized is False
