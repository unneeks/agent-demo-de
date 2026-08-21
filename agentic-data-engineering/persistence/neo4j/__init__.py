"""Neo4j adapter for the graph plane. Requires the ``neo4j`` extra."""

from persistence.neo4j.repository import Neo4jGraphRepository, Neo4jUnavailableError

__all__ = ["Neo4jGraphRepository", "Neo4jUnavailableError"]
