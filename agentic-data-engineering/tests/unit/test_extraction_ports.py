"""Structural conformance of every `ExtractionClient` backend to the port.

Mirrors `tests/unit/test_ports.py`. Purely static (`inspect`), so this never
instantiates `AnthropicExtractionClient` or `CopilotCliExtractionClient` --
neither the `anthropic` package nor a `copilot`/`gh` binary is required for
this file to run.
"""

from __future__ import annotations

import inspect

from discovery.extraction.anthropic_client import AnthropicExtractionClient
from discovery.extraction.client import ExtractionClient
from discovery.extraction.copilot_cli_client import CopilotCliExtractionClient
from discovery.extraction.replay_client import ReplayExtractionClient

ADAPTERS = [AnthropicExtractionClient, CopilotCliExtractionClient, ReplayExtractionClient]


def _signature(func: object) -> list[tuple[str, object]]:
    signature = inspect.signature(func)  # type: ignore[arg-type]
    return [
        (name, parameter.kind)
        for name, parameter in signature.parameters.items()
        if name != "self"
    ]


class TestExtractionClientAdaptersConform:
    def test_protocol_declares_extract(self) -> None:
        assert callable(getattr(ExtractionClient, "extract", None))

    def test_every_adapter_implements_extract(self) -> None:
        for adapter in ADAPTERS:
            assert callable(getattr(adapter, "extract", None)), f"{adapter.__name__} is missing extract()"

    def test_every_adapter_signature_matches_the_port(self) -> None:
        expected = _signature(ExtractionClient.extract)
        for adapter in ADAPTERS:
            actual = _signature(adapter.extract)
            assert actual == expected, f"{adapter.__name__}.extract diverges from the port"

    def test_replay_client_satisfies_the_runtime_protocol_without_instantiating_live_clients(
        self, tmp_path
    ) -> None:
        assert isinstance(ReplayExtractionClient(tmp_path), ExtractionClient)


class TestAdaptersDegradeGracefully:
    """Importing a live-backend adapter module must never require its
    driver (the `anthropic` package, a `copilot`/`gh` binary) to be present."""

    def test_anthropic_client_module_imports_without_the_package_installed(self) -> None:
        from discovery.extraction.errors import ExtractionError

        assert issubclass(ExtractionError, Exception)

    def test_anthropic_client_construction_without_an_api_key_fails_clearly(self, monkeypatch) -> None:
        from discovery.extraction.errors import ExtractionError

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        try:
            AnthropicExtractionClient()
        except ExtractionError as exc:
            assert "ANTHROPIC_API_KEY" in str(exc)
        else:
            raise AssertionError("expected ExtractionError without an API key")

    def test_copilot_cli_client_construction_without_the_binary_fails_clearly(self, monkeypatch) -> None:
        from discovery.extraction.errors import ExtractionError

        monkeypatch.setattr("shutil.which", lambda name: None)
        try:
            CopilotCliExtractionClient()
        except ExtractionError as exc:
            assert "PATH" in str(exc)
        else:
            raise AssertionError("expected ExtractionError without copilot/gh on PATH")
