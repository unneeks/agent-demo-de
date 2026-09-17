"""Structural conformance of every adapter to its port.

The behavioural contract lives in ``tests/contract``, but that suite can only
exercise an adapter when its server is reachable. These checks are static, so a
renamed method or changed signature is caught on every run -- including for the
Neo4j adapter in environments where no Neo4j is available.
"""

from __future__ import annotations

import inspect
from typing import Protocol, get_type_hints

import pytest

from persistence.memory import InMemoryGraphRepository, InMemoryMetadataRepository
from persistence.neo4j.repository import Neo4jGraphRepository
from persistence.ports import GraphRepository, MetadataRepository
from persistence.postgres.repository import PostgresMetadataRepository

GRAPH_ADAPTERS = [InMemoryGraphRepository, Neo4jGraphRepository]
METADATA_ADAPTERS = [InMemoryMetadataRepository, PostgresMetadataRepository]


def _protocol_methods(protocol: type[Protocol]) -> list[str]:
    return [
        name
        for name in dir(protocol)
        if not name.startswith("_") and callable(getattr(protocol, name, None))
    ]


def _signature(func: object) -> list[tuple[str, object]]:
    """Parameter names and kinds, ignoring annotations and defaults.

    Annotations are excluded deliberately: an adapter may legitimately narrow a
    return type. Names and kinds are what callers depend on.
    """
    signature = inspect.signature(func)  # type: ignore[arg-type]
    return [
        (name, parameter.kind)
        for name, parameter in signature.parameters.items()
        if name != "self"
    ]


class TestGraphAdaptersConform:
    @pytest.mark.parametrize("adapter", GRAPH_ADAPTERS, ids=lambda a: a.__name__)
    @pytest.mark.parametrize("method", _protocol_methods(GraphRepository))
    def test_method_is_implemented(self, adapter, method) -> None:
        assert callable(getattr(adapter, method, None)), (
            f"{adapter.__name__} is missing {method}()"
        )

    @pytest.mark.parametrize("adapter", GRAPH_ADAPTERS, ids=lambda a: a.__name__)
    @pytest.mark.parametrize("method", _protocol_methods(GraphRepository))
    def test_signature_matches(self, adapter, method) -> None:
        expected = _signature(getattr(GraphRepository, method))
        actual = _signature(getattr(adapter, method))
        assert actual == expected, f"{adapter.__name__}.{method} diverges from the port"

    def test_in_memory_satisfies_the_runtime_protocol(self) -> None:
        assert isinstance(InMemoryGraphRepository(), GraphRepository)


class TestMetadataAdaptersConform:
    @pytest.mark.parametrize("adapter", METADATA_ADAPTERS, ids=lambda a: a.__name__)
    @pytest.mark.parametrize("method", _protocol_methods(MetadataRepository))
    def test_method_is_implemented(self, adapter, method) -> None:
        assert callable(getattr(adapter, method, None)), (
            f"{adapter.__name__} is missing {method}()"
        )

    @pytest.mark.parametrize("adapter", METADATA_ADAPTERS, ids=lambda a: a.__name__)
    @pytest.mark.parametrize("method", _protocol_methods(MetadataRepository))
    def test_signature_matches(self, adapter, method) -> None:
        expected = _signature(getattr(MetadataRepository, method))
        actual = _signature(getattr(adapter, method))
        assert actual == expected, f"{adapter.__name__}.{method} diverges from the port"

    def test_in_memory_satisfies_the_runtime_protocol(self) -> None:
        assert isinstance(InMemoryMetadataRepository(), MetadataRepository)


class TestAdaptersDegradeGracefully:
    """Importing an adapter must never require its driver to be installed."""

    def test_neo4j_module_imports_without_a_server(self) -> None:
        from persistence.neo4j import Neo4jUnavailableError

        assert issubclass(Neo4jUnavailableError, RuntimeError)

    def test_postgres_module_imports_without_a_server(self) -> None:
        from persistence.postgres import PostgresUnavailableError

        assert issubclass(PostgresUnavailableError, RuntimeError)


class TestPortsAreTyped:
    def test_traversal_result_exposes_confidence_and_path(self) -> None:
        from persistence.ports import TraversalResult

        hints = get_type_hints(TraversalResult)
        assert {"confidence", "path", "depth"} <= set(hints)
