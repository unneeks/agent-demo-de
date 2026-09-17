"""Adapter fixtures for the contract suite.

Every adapter is offered to the same tests. The in-memory ones always run; the
Neo4j and PostgreSQL ones run only when the service is reachable and skip
cleanly otherwise, so ``pytest`` works with or without ``docker compose up``.

Connection details come from the environment, defaulting to docker-compose:

    ADE_NEO4J_URI / ADE_NEO4J_USER / ADE_NEO4J_PASSWORD
    ADE_POSTGRES_DSN
"""

from __future__ import annotations

import os
import socket
from collections.abc import Iterator
from urllib.parse import urlparse

import pytest

from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository

NEO4J_URI = os.environ.get("ADE_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("ADE_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("ADE_NEO4J_PASSWORD", "devpassword")
POSTGRES_DSN = os.environ.get(
    "ADE_POSTGRES_DSN", "postgresql://ade:devpassword@localhost:5432/ade"
)


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Cheap reachability probe.

    A TCP check rather than a real connection: it costs milliseconds when
    nothing is listening, which is the common case, and keeps a developer
    without Docker from waiting on driver timeouts.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def neo4j_available() -> bool:
    parsed = urlparse(NEO4J_URI)
    return _port_open(parsed.hostname or "localhost", parsed.port or 7687)


def postgres_available() -> bool:
    parsed = urlparse(POSTGRES_DSN)
    if parsed.scheme and parsed.hostname:
        return _port_open(parsed.hostname, parsed.port or 5432)
    # Unix-socket DSNs carry the host in the query string.
    return _port_open("localhost", 5432)


@pytest.fixture
def memory_graph() -> InMemoryGraphRepository:
    return InMemoryGraphRepository()


@pytest.fixture
def neo4j_graph() -> Iterator[object]:
    if not neo4j_available():
        pytest.skip(f"no Neo4j at {NEO4J_URI} (docker compose up -d neo4j)")
    try:
        from persistence.neo4j import Neo4jGraphRepository
    except ImportError:
        pytest.skip("neo4j driver not installed (pip install -e '.[neo4j]')")

    repo = Neo4jGraphRepository(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    repo.apply_constraints()
    repo.clear()
    try:
        yield repo
    finally:
        repo.clear()
        repo.close()


@pytest.fixture(params=["memory", "neo4j"])
def graph_repo(request: pytest.FixtureRequest) -> object:
    """Every graph adapter, one test run each."""
    return request.getfixturevalue(f"{request.param}_graph")


@pytest.fixture
def memory_metadata() -> InMemoryMetadataRepository:
    return InMemoryMetadataRepository()


@pytest.fixture
def postgres_metadata() -> Iterator[object]:
    if not postgres_available():
        pytest.skip(f"no PostgreSQL at {POSTGRES_DSN} (docker compose up -d postgres)")
    try:
        from persistence.postgres import PostgresMetadataRepository
    except ImportError:
        pytest.skip("psycopg not installed (pip install -e '.[postgres]')")

    repo = PostgresMetadataRepository(POSTGRES_DSN)
    repo.apply_migrations()
    # audit_ledger must be included: it is append-only by rule, so without an
    # explicit truncate its rows survive between pytest invocations, not just
    # between tests.
    with repo._conn.cursor() as cur:  # noqa: SLF001 - tests need a clean slate
        cur.execute(
            "TRUNCATE metamodel_entity, metamodel_relationship, context_bundle, "
            "gate_assessment, checklist_outcome, audit_ledger RESTART IDENTITY"
        )
    try:
        yield repo
    finally:
        repo.close()


@pytest.fixture(params=["memory", "postgres"])
def metadata_repo(request: pytest.FixtureRequest) -> object:
    """Every metadata adapter, one test run each."""
    return request.getfixturevalue(f"{request.param}_metadata")
