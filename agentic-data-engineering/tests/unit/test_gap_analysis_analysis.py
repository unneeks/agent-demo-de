"""`engines.gap_analysis.analysis.analyze_capability_gaps` -- the diff
between observed and desired maturity, and the recommended-role sourcing
per capability kind.
"""

from __future__ import annotations

from domain.metamodel.enums import EntityType, ProvenanceState
from engines.gap_analysis import analyze_capability_gaps

from tests.conftest import make_capability, make_delivery_capability, ref

PROJECT_REF = ref(EntityType.PROJECT, "demo")


class TestAnalyzeCapabilityGaps:
    def test_no_gap_when_current_meets_desired(self, registry) -> None:
        capability = make_capability("transformation", maturity=4)
        gaps = analyze_capability_gaps(PROJECT_REF, [capability], [], {"transformation": 4}, registry)
        assert gaps == []

    def test_no_gap_when_current_exceeds_desired(self, registry) -> None:
        capability = make_capability("transformation", maturity=4)
        gaps = analyze_capability_gaps(PROJECT_REF, [capability], [], {"transformation": 2}, registry)
        assert gaps == []

    def test_real_gap_when_current_below_desired(self, registry) -> None:
        capability = make_capability("transformation", maturity=1)
        [gap] = analyze_capability_gaps(PROJECT_REF, [capability], [], {"transformation": 4}, registry)
        assert gap.capability_key == "transformation"
        assert gap.current_maturity == 1
        assert gap.desired_maturity == 4
        assert gap.gap_size == 3
        assert gap.priority == 1  # gap_size >= 3
        assert gap.provenance is ProvenanceState.OBSERVED
        assert gap.capability_ref == capability.ref()

    def test_key_not_in_desired_maturity_is_skipped_not_an_error(self, registry) -> None:
        capability = make_capability("transformation", maturity=0)
        gaps = analyze_capability_gaps(PROJECT_REF, [capability], [], {}, registry)
        assert gaps == []

    def test_recommended_roles_for_a_technical_capability_reverse_scans_engineering_roles(
        self, registry
    ) -> None:
        capability = make_capability("transformation", maturity=0)
        [gap] = analyze_capability_gaps(PROJECT_REF, [capability], [], {"transformation": 2}, registry)
        expected = sorted(
            role.role_key
            for role in registry.engineering_roles.values()
            if "transformation" in role.required_capabilities
        )
        assert gap.recommended_role_keys == expected
        assert expected  # the worked registry really does name at least one role

    def test_recommended_roles_for_a_delivery_capability_uses_realized_by_roles_directly(
        self, registry
    ) -> None:
        delivery_capability = make_delivery_capability("regression-assurance", maturity=0)
        [gap] = analyze_capability_gaps(
            PROJECT_REF, [], [delivery_capability], {"regression-assurance": 3}, registry
        )
        assert gap.recommended_role_keys == list(
            registry.delivery_capabilities["regression-assurance"].realized_by_roles
        )
        assert gap.recommended_role_keys == ["regression-engineer"]

    def test_priority_scales_with_gap_size(self, registry) -> None:
        small = make_capability("transformation", maturity=3)
        [gap] = analyze_capability_gaps(PROJECT_REF, [small], [], {"transformation": 4}, registry)
        assert gap.priority == 3  # gap_size == 1

        medium = make_capability("transformation", "other-project", maturity=2)
        [gap2] = analyze_capability_gaps(
            ref(EntityType.PROJECT, "other-project"), [medium], [], {"transformation": 4}, registry
        )
        assert gap2.priority == 2  # gap_size == 2
