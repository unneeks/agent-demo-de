"""PostgreSQL adapter for the metadata plane. Requires the ``postgres`` extra."""

from persistence.postgres.repository import (
    PostgresMetadataRepository,
    PostgresUnavailableError,
)

__all__ = ["PostgresMetadataRepository", "PostgresUnavailableError"]
