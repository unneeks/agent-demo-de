"""Provenance invariants, including the addendum's inferred-cannot-block rule.

If these pass, it is not possible to construct a metamodel object that states a
guess as fact, claims human sign-off without naming the human, or lets text
extracted from a document stop a release.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.metamodel.base import Blockable, Provenanced, utc_now
from domain.metamodel.entities.delivery import ApprovalGate, ChecklistItem, Control, Standard
from domain.metamodel.enums import EntityType, ExtractionMethod, ProvenanceState
from tests.conftest import make_asset, make_pipeline, ref


class TestObserved:
    def test_confidence_defaults_to_certain(self) -> None:
        assert Provenanced(provenance=ProvenanceState.OBSERVED, discovered_by="git").confidence == 1.0

    def test_rejects_uncertain_observation(self) -> None:
        """An observation with doubt attached is an inference in disguise."""
        with pytest.raises(ValidationError, match="always have confidence 1.0"):
            Provenanced(
                provenance=ProvenanceState.OBSERVED, discovered_by="git", confidence=0.8
            )

    def test_requires_a_discoverer(self) -> None:
        with pytest.raises(ValidationError, match="must name discovered_by"):
            Provenanced(provenance=ProvenanceState.OBSERVED)


class TestInferred:
    def test_requires_confidence(self) -> None:
        with pytest.raises(ValidationError, match="must carry a confidence"):
            Provenanced(provenance=ProvenanceState.INFERRED)

    @pytest.mark.parametrize("bad", [-0.1, 1.1])
    def test_confidence_bounded(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            Provenanced(provenance=ProvenanceState.INFERRED, confidence=bad)

    def test_is_not_treated_as_fact(self) -> None:
        assert not Provenanced(provenance=ProvenanceState.INFERRED, confidence=0.99).is_factual


class TestHumanVerification:
    @pytest.mark.parametrize(
        "state", [ProvenanceState.HUMAN_VERIFIED, ProvenanceState.CERTIFIED]
    )
    def test_requires_a_named_human(self, state: ProvenanceState) -> None:
        with pytest.raises(ValidationError, match="requires human_verified_by"):
            Provenanced(provenance=state)

    def test_timestamps_the_signoff(self) -> None:
        signed = Provenanced(provenance=ProvenanceState.CERTIFIED, human_verified_by="alex")
        assert signed.human_verified_at is not None
        assert signed.is_factual


class TestDocumentProvenance:
    """Delivery metadata is extracted from prose and must stay attributable."""

    def test_semantic_extraction_requires_a_source_document(self) -> None:
        with pytest.raises(ValidationError, match="must name source_document"):
            Provenanced(
                provenance=ProvenanceState.INFERRED,
                confidence=0.7,
                extraction_method=ExtractionMethod.SEMANTIC_EXTRACTION,
            )

    def test_citation_resolves_to_document_and_section(self) -> None:
        fact = Provenanced(
            provenance=ProvenanceState.INFERRED,
            confidence=0.7,
            extraction_method=ExtractionMethod.SEMANTIC_EXTRACTION,
            source_document="ArchitectureStandards.pdf",
            source_section="4.2",
        )
        assert fact.citation == "ArchitectureStandards.pdf#4.2"

    def test_no_citation_when_nothing_was_extracted(self) -> None:
        assert Provenanced(provenance=ProvenanceState.INFERRED, confidence=0.5).citation is None


class TestInferredRulesCannotBlock:
    """The addendum's guardrail, made structural.

    Extracted process text may advise. Only verified process text may stop a
    release. Without this, a misread paragraph halts delivery and the platform
    loses the organization's trust permanently.
    """

    def _inferred(self) -> dict[str, object]:
        return {"provenance": ProvenanceState.INFERRED, "confidence": 0.75}

    def _verified(self) -> dict[str, object]:
        return {
            "provenance": ProvenanceState.HUMAN_VERIFIED,
            "human_verified_by": "governance-board",
        }

    def test_inferred_standard_cannot_block(self) -> None:
        with pytest.raises(ValidationError, match="cannot be blocking=True"):
            Standard(
                id="s",
                name="s",
                entity_type=EntityType.STANDARD,
                standard_key="s",
                statement="Models must be normalised.",
                blocking=True,
                **self._inferred(),
            )

    def test_inferred_standard_may_advise(self) -> None:
        standard = Standard(
            id="s",
            name="s",
            entity_type=EntityType.STANDARD,
            standard_key="s",
            statement="Models must be normalised.",
            blocking=False,
            **self._inferred(),
        )
        assert standard.blocking is False

    def test_verified_standard_may_block(self) -> None:
        standard = Standard(
            id="s",
            name="s",
            entity_type=EntityType.STANDARD,
            standard_key="s",
            statement="Models must be normalised.",
            blocking=True,
            **self._verified(),
        )
        assert standard.blocking is True

    def test_inferred_control_cannot_block(self) -> None:
        with pytest.raises(ValidationError, match="cannot be blocking=True"):
            Control(
                id="c",
                name="c",
                entity_type=EntityType.CONTROL,
                control_key="c",
                statement="All changes are approved.",
                blocking=True,
                **self._inferred(),
            )

    def test_inferred_checklist_item_cannot_block(self) -> None:
        with pytest.raises(ValidationError, match="cannot be blocking=True"):
            ChecklistItem(
                id="i",
                name="i",
                entity_type=EntityType.CHECKLIST_ITEM,
                item_key="i",
                checklist_key="c",
                blocking=True,
                **self._inferred(),
            )

    def test_inferred_gate_cannot_block(self) -> None:
        with pytest.raises(ValidationError, match="cannot be blocking=True"):
            ApprovalGate(
                id="g",
                name="g",
                entity_type=EntityType.APPROVAL_GATE,
                gate_key="g",
                required_role_keys=["data-architect"],
                blocking=True,
                **self._inferred(),
            )

    def test_extracted_gate_starts_advisory_and_can_be_promoted(self) -> None:
        """The intended workflow: extract as advisory, verify, then it blocks."""
        extracted = ApprovalGate(
            id="g",
            name="Architecture Review",
            entity_type=EntityType.APPROVAL_GATE,
            gate_key="g",
            required_role_keys=["data-architect"],
            blocking=False,
            extraction_method=ExtractionMethod.SEMANTIC_EXTRACTION,
            source_document="DeliveryHandbook.pdf",
            source_section="Section 6",
            **self._inferred(),
        )
        assert not extracted.blocking
        assert extracted.citation == "DeliveryHandbook.pdf#Section 6"

        promoted = extracted.model_copy(
            update={
                "provenance": ProvenanceState.HUMAN_VERIFIED,
                "human_verified_by": "process-owner",
                "confidence": None,
                "blocking": True,
            }
        )
        # model_copy skips validation, so re-validate to prove the promoted form
        # is genuinely legal rather than merely constructed.
        assert ApprovalGate.model_validate(promoted.model_dump()).blocking is True


class TestBlockableWithoutProvenance:
    """Blockable is usable on types that carry no provenance at all."""

    def test_plain_blockable_may_block(self) -> None:
        assert Blockable(blocking=True).blocking is True


class TestDiscoveredEntitiesInheritTheInvariant:
    def test_pipeline_cannot_be_inferred_without_confidence(self) -> None:
        with pytest.raises(ValidationError, match="must carry a confidence"):
            make_pipeline("stg_customers", provenance=ProvenanceState.INFERRED, confidence=None)

    def test_asset_records_its_discoverer(self) -> None:
        asset = make_asset("raw.customers")
        assert asset.discovered_by and asset.is_factual

    def test_validity_window_must_not_invert(self) -> None:
        now = utc_now()
        with pytest.raises(ValidationError, match="must not precede"):
            make_asset(
                "raw.customers",
                valid_from=now,
                valid_until=now.replace(year=now.year - 1),
            )


class TestEntityRef:
    def test_round_trips_through_string_form(self) -> None:
        original = ref(EntityType.AGENT, "regression-agent", "1.2.0")
        assert type(original).parse(str(original)) == original

    def test_identity_strips_the_version(self) -> None:
        pinned = ref(EntityType.AGENT, "a", "1.0.0")
        assert pinned.identity == ref(EntityType.AGENT, "a")

    def test_malformed_reference_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be of the form"):
            type(ref(EntityType.AGENT, "a")).parse("no-type-prefix")
