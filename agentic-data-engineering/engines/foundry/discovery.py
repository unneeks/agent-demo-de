"""``discover_patterns()`` -- deterministic, crude-by-design grouping of
``EngineeringObservation``s into ``EngineeringPattern``s.

Pure: no I/O, no LLM. This is literal field-value grouping plus
set-overlap scoring, **not semantic clustering** -- two pipelines that do
the same thing under different ``pipeline_kind`` strings will never group.
That limitation is deliberate for a v1 with no LLM in this step (mining
and grouping are the two steps the user confirmed must stay
deterministic; only candidate *content* synthesis calls an LLM -- see
``foundry/synthesis/``) and is asserted by a dedicated test, not hidden.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.foundry import EngineeringObservation, EngineeringPattern
from domain.metamodel.enums import ProvenanceState

DISCOVERED_BY = "foundry-discovery@0.1.0"

_CATEGORY_BY_SOURCE_TYPE = {
    "pipeline": "pipeline_shape",
    "test": "test_coverage_shape",
    "delivery_task": "delivery_staffing_shape",
    "delivery_activity": "delivery_staffing_shape",
}


def _grouping_key(observation: EngineeringObservation) -> tuple[str, str, str | None]:
    return (observation.source_type, observation.activity, observation.technology)


def _io_set(observation: EngineeringObservation) -> set[str]:
    return set(observation.inputs) | set(observation.outputs)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def _average_pairwise_jaccard(observations: list[EngineeringObservation]) -> float:
    io_sets = [_io_set(observation) for observation in observations]
    pairs = list(combinations(range(len(io_sets)), 2))
    if not pairs:
        return 1.0
    return sum(_jaccard(io_sets[i], io_sets[j]) for i, j in pairs) / len(pairs)


def _intersect(observations: list[EngineeringObservation], attr: str) -> list[str]:
    sets = [set(getattr(observation, attr)) for observation in observations]
    common = set.intersection(*sets) if sets else set()
    return sorted(common)


def _known_variations(observations: list[EngineeringObservation], attr: str, common: list[str]) -> list[str]:
    """Values present in some but not all grouped observations -- noted,
    never silently dropped by the intersection that produces the common set.
    """
    common_set = set(common)
    counts: dict[str, int] = defaultdict(int)
    for observation in observations:
        for value in getattr(observation, attr):
            if value not in common_set:
                counts[value] += 1
    return [
        f"{attr} {value!r} present in {count} of {len(observations)} observations"
        for value, count in sorted(counts.items())
    ]


def discover_patterns(
    observations: list[EngineeringObservation],
    *,
    project_ref: EntityRef,
    min_frequency: int = 2,
    discovered_by: str = DISCOVERED_BY,
) -> list[EngineeringPattern]:
    """Group observations by exact-match ``(source_type, activity,
    technology)``; a group of size >= ``min_frequency`` becomes one pattern.

    ``pattern_key`` is a deterministic slug derived from the grouping key,
    so the same input always produces the same key.
    """
    groups: dict[tuple[str, str, str | None], list[EngineeringObservation]] = defaultdict(list)
    for observation in observations:
        groups[_grouping_key(observation)].append(observation)

    patterns: list[EngineeringPattern] = []
    for (source_type, activity, technology), members in sorted(
        groups.items(), key=lambda item: (item[0][0], item[0][1], item[0][2] or "")
    ):
        if len(members) < min_frequency:
            continue
        category = _CATEGORY_BY_SOURCE_TYPE.get(source_type, "pipeline_shape")
        common_inputs = _intersect(members, "inputs")
        common_outputs = _intersect(members, "outputs")
        variations = [
            *_known_variations(members, "inputs", common_inputs),
            *_known_variations(members, "outputs", common_outputs),
        ]
        similarity = _average_pairwise_jaccard(members)
        pattern_key = f"pattern.{category}.{activity}.{technology or 'none'}"
        patterns.append(
            EngineeringPattern(
                name=f"pattern: {activity} ({technology or 'no technology'})",
                project_ref=project_ref,
                pattern_key=pattern_key,
                category=category,
                observation_refs=[observation.ref() for observation in members],
                frequency=len(members),
                common_activity=activity,
                common_technology=technology,
                common_inputs=common_inputs,
                common_outputs=common_outputs,
                known_variations=variations,
                similarity_score=similarity,
                provenance=ProvenanceState.INFERRED,
                confidence=similarity,
                discovered_by=discovered_by,
            )
        )
    return patterns
