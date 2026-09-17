"""Base types shared by every entity in both twins.

Four ideas carry the weight:

* **References, not object graphs.** Entities point at each other through
  :class:`EntityRef`, so any entity serializes, versions and diffs on its own.
* **Provenance is structural.** :class:`Provenanced` makes it impossible to
  record an inference without a confidence, or to claim human sign-off without
  naming the human. See ADR-0003.
* **Extraction is remembered.** Delivery metadata is largely read out of prose,
  so :class:`Provenanced` also carries where it was read from and how.
* **Blocking requires verification.** :class:`Blockable` refuses to let an
  inferred rule stop delivery. See ADR-0009.
"""

from __future__ import annotations

import os
import re
import secrets
import time
from datetime import UTC, datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.metamodel.enums import (
    BLOCKING_PROVENANCE,
    EntityType,
    ExtractionMethod,
    ProvenanceState,
    Twin,
)
from domain.metamodel.version import METAMODEL_VERSION

# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------

SEMVER_PATTERN = (
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

SemVer = Annotated[str, Field(pattern=SEMVER_PATTERN, examples=["1.0.0", "2.1.0-rc.1"])]

_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    """A time-sortable identifier for instance entities.

    Evidence, events, decisions and approvals are created in volume and almost
    always read in time order, so they use a lexicographically sortable id
    rather than a random UUID. 48 bits of millisecond timestamp then 80 bits of
    randomness, Crockford base32.

    Honours ``ADE_ULID_SEED_TIME_MS`` so tests can pin the timestamp half.
    """
    seeded = os.environ.get("ADE_ULID_SEED_TIME_MS")
    timestamp_ms = int(seeded) if seeded else int(time.time() * 1000)
    value = (timestamp_ms << 80) | secrets.randbits(80)
    chars = []
    for _ in range(26):
        value, remainder = divmod(value, 32)
        chars.append(_CROCKFORD32[remainder])
    return "".join(reversed(chars))


def utc_now() -> datetime:
    """Timezone-aware current time. All metamodel timestamps are UTC."""
    return datetime.now(UTC)


def is_valid_semver(value: str) -> bool:
    return re.match(SEMVER_PATTERN, value) is not None


# --------------------------------------------------------------------------
# Model roots
# --------------------------------------------------------------------------


class MetamodelModel(BaseModel):
    """Root config for every metamodel type.

    ``extra="forbid"`` matters more than it looks: discovery adapters populate
    these from parsed repositories and documents, and a silently accepted
    unknown field is a discovered fact dropped on the floor.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
        str_strip_whitespace=True,
    )


class EntityRef(MetamodelModel):
    """A typed, optionally version-pinned pointer to another entity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: EntityType
    id: str = Field(min_length=1, max_length=256)
    version: SemVer | None = Field(
        default=None, description="Pin to an exact version. None means 'whatever is current'."
    )

    def __str__(self) -> str:
        return f"{self.type.value}:{self.id}" + (f"@{self.version}" if self.version else "")

    @property
    def identity(self) -> EntityRef:
        """The unversioned form -- how the graph plane keys this node."""
        return self if self.version is None else EntityRef(type=self.type, id=self.id)

    @classmethod
    def parse(cls, value: str) -> EntityRef:
        """Parse the ``Type:id@version`` form used across the YAML registries."""
        if ":" not in value:
            raise ValueError(f"entity reference {value!r} must be of the form 'Type:id[@version]'")
        type_part, _, rest = value.partition(":")
        id_part, _, version_part = rest.partition("@")
        return cls(type=EntityType(type_part), id=id_part, version=version_part or None)


class Identified(MetamodelModel):
    """An entity with a stable identity and a human-readable name."""

    id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=512)
    description: str | None = None

    #: Set by each concrete entity; drives ``ref()`` and registry validation.
    entity_type: EntityType
    #: Which dimension of the twin this belongs to. Navigation, not partition.
    twin: Twin = Twin.SHARED

    def ref(self, *, pinned: bool = False) -> EntityRef:
        """A reference to this entity.

        ``pinned=True`` includes the version -- what audit records and
        reproducibility snapshots want. The default floating ref is what
        configuration wants.
        """
        version = getattr(self, "version", None) if pinned else None
        return EntityRef(type=self.entity_type, id=self.id, version=version)


class Versioned(MetamodelModel):
    """The entity's own version plus the metamodel version it was written under.

    Storing ``metamodel_version`` on the record -- rather than assuming the
    reader's -- is what lets an old row still be interpreted after the contract
    moves on.
    """

    version: SemVer = "0.1.0"
    metamodel_version: SemVer = Field(default=METAMODEL_VERSION)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime | None = None


class Provenanced(MetamodelModel):
    """Where a fact came from and how much it should be trusted.

    The validator is the executable form of "evidence over inference":

    * ``OBSERVED`` -- seen directly. Confidence is 1.0 by definition and a
      discoverer must be named.
    * ``INFERRED`` -- concluded. A confidence score is *mandatory*.
    * ``HUMAN_VERIFIED`` / ``CERTIFIED`` -- a named human signed off, timestamped.

    The document fields exist because the Delivery Twin is largely extracted
    from prose. A gate rule read out of a Confluence paragraph must be able to
    say which paragraph, or nobody can check it.
    """

    provenance: ProvenanceState
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_refs: list[EntityRef] = Field(default_factory=list)
    discovered_by: str | None = Field(
        default=None,
        description="Adapter, skill or agent that produced this, e.g. 'git-discovery@0.1.0'.",
    )
    discovered_at: datetime = Field(default_factory=utc_now)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    human_verified_by: str | None = None
    human_verified_at: datetime | None = None

    # -- document provenance (delivery twin) ------------------------------
    source_document: str | None = Field(
        default=None, description="Document this was extracted from -- path, URI or document id."
    )
    source_section: str | None = Field(
        default=None, description="Section, heading or page within the source document."
    )
    extraction_method: ExtractionMethod | None = None

    @model_validator(mode="before")
    @classmethod
    def _apply_provenance_defaults(cls, data: Any) -> Any:
        """Fill what follows necessarily from the provenance state.

        Done before validation rather than by mutating a built model, so the
        result is a normally-constructed instance and assignment validation
        stays on.
        """
        if not isinstance(data, dict):
            return data
        raw = data.get("provenance")
        try:
            state = ProvenanceState(raw) if raw is not None else None
        except ValueError:
            return data  # let field validation report the bad value

        if state is ProvenanceState.OBSERVED and data.get("confidence") is None:
            data["confidence"] = 1.0
        if (
            state in (ProvenanceState.HUMAN_VERIFIED, ProvenanceState.CERTIFIED)
            and data.get("human_verified_at") is None
        ):
            data["human_verified_at"] = utc_now()
        return data

    @model_validator(mode="after")
    def _enforce_provenance_invariants(self) -> Self:
        state = self.provenance

        if state is ProvenanceState.OBSERVED:
            if self.confidence != 1.0:
                raise ValueError(
                    "OBSERVED facts are seen directly and always have confidence 1.0; "
                    f"got {self.confidence}. Use INFERRED if this was concluded rather than seen."
                )
            if not self.discovered_by:
                raise ValueError("OBSERVED facts must name discovered_by (what saw this).")

        if state is ProvenanceState.INFERRED and self.confidence is None:
            raise ValueError(
                "INFERRED facts must carry a confidence score. An inference without a "
                "confidence is indistinguishable from an observation."
            )

        if state in (ProvenanceState.HUMAN_VERIFIED, ProvenanceState.CERTIFIED):
            if not self.human_verified_by:
                raise ValueError(f"{state.value} requires human_verified_by (who signed off).")

        if self.extraction_method is ExtractionMethod.SEMANTIC_EXTRACTION and not self.source_document:
            raise ValueError(
                "semantically extracted facts must name source_document; an unattributable "
                "reading of a document cannot be checked by a human."
            )

        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not precede valid_from.")

        return self

    @property
    def is_factual(self) -> bool:
        """Whether this may be treated as fact rather than as a hypothesis."""
        return self.provenance is not ProvenanceState.INFERRED

    @property
    def citation(self) -> str | None:
        """Human-readable pointer to where this came from, if anywhere."""
        if not self.source_document:
            return None
        return f"{self.source_document}#{self.source_section}" if self.source_section else self.source_document


class Blockable(MetamodelModel):
    """Mixin for rules that can stop delivery.

    The addendum is explicit that inferred information must never silently
    become certified organizational policy. This makes that structural: a rule
    read out of a document by an extractor may *advise*, but it cannot *block*
    until a human has verified it.

    Applies to Standard, Control, ApprovalRule, ChecklistItem and ApprovalGate --
    everything with the power to halt a change.
    """

    blocking: bool = Field(
        default=False,
        description="Whether failing this rule stops delivery. Requires verified provenance.",
    )

    @model_validator(mode="after")
    def _blocking_requires_verified_provenance(self) -> Self:
        provenance = getattr(self, "provenance", None)
        if self.blocking and provenance is not None and provenance not in BLOCKING_PROVENANCE:
            raise ValueError(
                f"a rule with provenance {provenance.value} cannot be blocking=True. "
                "Inferred rules may advise, but only an OBSERVED or human-verified rule may "
                "stop delivery -- extracted text must never silently become enforced policy."
            )
        return self


# --------------------------------------------------------------------------
# Entity roots
# --------------------------------------------------------------------------


class MetamodelEntity(Identified, Versioned):
    """Base for catalog entities addressed by slug plus semver."""

    labels: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Adapter-specific detail that has not earned a first-class field yet.",
    )


class ProvenancedEntity(MetamodelEntity, Provenanced):
    """Base for discovered entities, which always carry provenance.

    Everything the platform learns -- about the technical system *or* about the
    organization's delivery process -- is discovered rather than declared, so it
    inherits from here and cannot omit how it came to be known.
    """
