"""PostgreSQL adapter for the metadata plane.

Mirrors the in-memory adapter exactly -- the same contract suite runs against
both, so any divergence shows up as a test failure rather than as a production
surprise.

``psycopg`` is imported lazily so this module can be imported without the
``postgres`` extra installed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from domain.metamodel.entities.shared.work import Decision
from domain.metamodel.enums import EntityType
from domain.metamodel.relationships import Relationship
from domain.metamodel.version import METAMODEL_VERSION
from persistence.memory.repositories import content_hash
from persistence.ports import AuditEntry, StoredEntity

_GENESIS_HASH = "0" * 64


class PostgresUnavailableError(RuntimeError):
    """psycopg is not installed, or the server is unreachable."""


class PostgresMetadataRepository:
    """Metadata-plane adapter. Implements the ``MetadataRepository`` protocol."""

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.types.json import Jsonb
        except ImportError as exc:  # pragma: no cover - only without the extra
            raise PostgresUnavailableError(
                "psycopg is not installed; install with the 'postgres' extra"
            ) from exc
        self._jsonb = Jsonb
        self._conn = psycopg.connect(dsn, autocommit=True)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> PostgresMetadataRepository:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def apply_migrations(self, migrations_dir: str | None = None) -> list[str]:
        """Apply every ``*.sql`` migration in order. Idempotent."""
        directory = Path(migrations_dir) if migrations_dir else Path(__file__).parent / "migrations"
        applied: list[str] = []
        for path in sorted(directory.glob("*.sql")):
            with self._conn.cursor() as cur:
                cur.execute(path.read_text(encoding="utf-8"))
            applied.append(path.name)
        return applied

    # -- entities ---------------------------------------------------------

    def upsert(self, entity: object) -> StoredEntity:
        payload: dict[str, Any] = entity.model_dump(mode="json")  # type: ignore[attr-defined]
        entity_type = EntityType(payload["entity_type"])
        entity_id = str(payload["id"])
        version = str(payload.get("version", "0.1.0"))
        digest = content_hash(payload)
        twin = str(payload.get("twin", "SHARED"))

        with self._conn.cursor() as cur:
            # Demote any other current version first; the partial unique index
            # allows only one current row per entity.
            cur.execute(
                """
                UPDATE metamodel_entity SET is_current = FALSE
                WHERE entity_type = %s AND entity_id = %s AND version <> %s AND is_current
                """,
                (entity_type.value, entity_id, version),
            )
            cur.execute(
                """
                INSERT INTO metamodel_entity (
                    entity_type, entity_id, version, metamodel_version, twin,
                    payload, content_hash, is_current
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (entity_type, entity_id, version) DO UPDATE
                SET payload = EXCLUDED.payload,
                    content_hash = EXCLUDED.content_hash,
                    metamodel_version = EXCLUDED.metamodel_version,
                    twin = EXCLUDED.twin,
                    is_current = TRUE,
                    updated_at = now()
                """,
                (
                    entity_type.value,
                    entity_id,
                    version,
                    str(payload.get("metamodel_version", METAMODEL_VERSION)),
                    twin,
                    self._jsonb(payload),
                    digest,
                ),
            )

        return StoredEntity(
            entity_type=entity_type,
            entity_id=entity_id,
            version=version,
            metamodel_version=str(payload.get("metamodel_version", METAMODEL_VERSION)),
            payload=payload,
            content_hash=digest,
            is_current=True,
        )

    @staticmethod
    def _row_to_stored(row: tuple[Any, ...]) -> StoredEntity:
        return StoredEntity(
            entity_type=EntityType(row[0]),
            entity_id=row[1],
            version=row[2],
            metamodel_version=row[3],
            payload=row[4],
            content_hash=row[5],
            is_current=row[6],
        )

    _SELECT = (
        "SELECT entity_type, entity_id, version, metamodel_version, payload, "
        "content_hash, is_current FROM metamodel_entity"
    )

    def get(
        self, entity_type: EntityType, entity_id: str, version: str | None = None
    ) -> StoredEntity | None:
        with self._conn.cursor() as cur:
            if version is not None:
                cur.execute(
                    f"{self._SELECT} WHERE entity_type = %s AND entity_id = %s AND version = %s",
                    (entity_type.value, entity_id, version),
                )
            else:
                cur.execute(
                    f"{self._SELECT} WHERE entity_type = %s AND entity_id = %s AND is_current",
                    (entity_type.value, entity_id),
                )
            row = cur.fetchone()
        return self._row_to_stored(row) if row else None

    def list(self, entity_type: EntityType, *, current_only: bool = True) -> list[StoredEntity]:
        clause = " AND is_current" if current_only else ""
        with self._conn.cursor() as cur:
            cur.execute(
                f"{self._SELECT} WHERE entity_type = %s{clause} ORDER BY entity_id, version",
                (entity_type.value,),
            )
            return [self._row_to_stored(row) for row in cur.fetchall()]

    def versions(self, entity_type: EntityType, entity_id: str) -> list[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT version FROM metamodel_entity WHERE entity_type = %s AND entity_id = %s "
                "ORDER BY version",
                (entity_type.value, entity_id),
            )
            return [row[0] for row in cur.fetchall()]

    def delete(self, entity_type: EntityType, entity_id: str, version: str | None = None) -> bool:
        with self._conn.cursor() as cur:
            if version is not None:
                cur.execute(
                    "DELETE FROM metamodel_entity WHERE entity_type = %s AND entity_id = %s "
                    "AND version = %s",
                    (entity_type.value, entity_id, version),
                )
            else:
                cur.execute(
                    "DELETE FROM metamodel_entity WHERE entity_type = %s AND entity_id = %s",
                    (entity_type.value, entity_id),
                )
            return cur.rowcount > 0

    # -- relationships (durable log the graph plane is rebuilt from) -------

    def upsert_relationship(self, rel: Relationship) -> None:
        payload = rel.model_dump(mode="json")
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO metamodel_relationship (
                    relationship_id, rel_type, source_type, source_id,
                    target_type, target_id, provenance, confidence,
                    discovered_by, discovered_at, valid_from, valid_until,
                    human_verified_by, human_verified_at,
                    source_document, source_section, extraction_method,
                    attributes, payload
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (source_type, source_id, rel_type, target_type, target_id)
                DO UPDATE SET
                    provenance = EXCLUDED.provenance,
                    confidence = EXCLUDED.confidence,
                    discovered_by = EXCLUDED.discovered_by,
                    discovered_at = EXCLUDED.discovered_at,
                    human_verified_by = EXCLUDED.human_verified_by,
                    human_verified_at = EXCLUDED.human_verified_at,
                    source_document = EXCLUDED.source_document,
                    source_section = EXCLUDED.source_section,
                    extraction_method = EXCLUDED.extraction_method,
                    attributes = EXCLUDED.attributes,
                    payload = EXCLUDED.payload
                """,
                (
                    rel.id,
                    rel.type,
                    rel.source.type.value,
                    rel.source.id,
                    rel.target.type.value,
                    rel.target.id,
                    rel.provenance.value,
                    rel.confidence,
                    rel.discovered_by,
                    rel.discovered_at,
                    rel.valid_from,
                    rel.valid_until,
                    rel.human_verified_by,
                    rel.human_verified_at,
                    rel.source_document,
                    rel.source_section,
                    rel.extraction_method.value if rel.extraction_method else None,
                    self._jsonb(rel.attributes),
                    self._jsonb(payload),
                ),
            )

    def all_relationships(self) -> list[Relationship]:
        """Every stored edge -- the input to rebuilding the graph plane."""
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM metamodel_relationship ORDER BY relationship_id")
            return [Relationship.model_validate(row[0]) for row in cur.fetchall()]

    # -- audit ------------------------------------------------------------

    def append_audit(self, decision: Decision) -> AuditEntry:
        payload = decision.model_dump(mode="json")
        with self._conn.cursor() as cur:
            cur.execute("SELECT entry_hash FROM audit_ledger ORDER BY sequence DESC LIMIT 1")
            row = cur.fetchone()
            previous = row[0] if row else _GENESIS_HASH
            entry_hash = hashlib.sha256(
                (previous + content_hash(payload)).encode("utf-8")
            ).hexdigest()
            cur.execute(
                """
                INSERT INTO audit_ledger (decision_id, entry_hash, previous_hash, payload)
                VALUES (%s, %s, %s, %s)
                RETURNING sequence
                """,
                (decision.id, entry_hash, None if row is None else previous, self._jsonb(payload)),
            )
            sequence = cur.fetchone()[0]

        return AuditEntry(
            sequence=sequence,
            decision_id=decision.id,
            entry_hash=entry_hash,
            previous_hash=None if row is None else previous,
            payload=payload,
        )

    def audit_entries(self) -> list[AuditEntry]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT sequence, decision_id, entry_hash, previous_hash, payload "
                "FROM audit_ledger ORDER BY sequence"
            )
            rows = cur.fetchall()
        # BIGSERIAL starts at 1; the contract numbers entries from 0.
        return [
            AuditEntry(
                sequence=index,
                decision_id=row[1],
                entry_hash=row[2],
                previous_hash=row[3],
                payload=row[4],
            )
            for index, row in enumerate(rows)
        ]

    def verify_audit_chain(self) -> bool:
        previous = _GENESIS_HASH
        for entry in self.audit_entries():
            expected = hashlib.sha256(
                (previous + content_hash(entry.payload)).encode("utf-8")
            ).hexdigest()
            if expected != entry.entry_hash:
                return False
            previous = entry.entry_hash
        return True
