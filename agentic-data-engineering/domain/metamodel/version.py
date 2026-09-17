"""Metamodel versioning and compatibility.

The metamodel is a published contract: discovery adapters write against it,
stored rows are stamped with it, and reproducibility snapshots pin it.

Semver applied to a schema:

* **patch** -- documentation and descriptions.
* **minor** -- additive and backward compatible. Old records still validate.
* **major** -- breaking. Old records may need migration.

A reader can interpret any record whose major version matches its own and whose
minor version is not ahead of its own.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Current metamodel version, stamped onto every persisted entity. Must equal
#: the value in ``metamodel-registry/metamodel.version.yaml``; a test enforces it.
METAMODEL_VERSION = "0.1.0"


class MetamodelCompatibilityError(Exception):
    """A record cannot be safely interpreted by this reader."""


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> Version:
        core = value.split("-", 1)[0].split("+", 1)[0]
        parts = core.split(".")
        if len(parts) != 3:
            raise ValueError(f"{value!r} is not a valid semantic version")
        try:
            return cls(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError as exc:
            raise ValueError(f"{value!r} is not a valid semantic version") from exc

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def is_compatible(record_version: str, reader_version: str = METAMODEL_VERSION) -> bool:
    """Whether ``reader_version`` can safely interpret ``record_version``."""
    record = Version.parse(record_version)
    reader = Version.parse(reader_version)
    return record.major == reader.major and record.minor <= reader.minor


def require_compatible(record_version: str, reader_version: str = METAMODEL_VERSION) -> None:
    if not is_compatible(record_version, reader_version):
        raise MetamodelCompatibilityError(
            f"record written under metamodel {record_version} cannot be interpreted by "
            f"reader at metamodel {reader_version}"
        )
