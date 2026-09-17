"""Agent-based extraction: one `ExtractionClient` Protocol, three backends.

`AnthropicExtractionClient` and `CopilotCliExtractionClient` are live
backends; `ReplayExtractionClient` serves committed golden fixtures for
hermetic tests. `discovery.orchestrate` depends only on the Protocol.
"""

from discovery.extraction.anthropic_client import AnthropicExtractionClient
from discovery.extraction.client import ExtractionClient
from discovery.extraction.copilot_cli_client import CopilotCliExtractionClient
from discovery.extraction.errors import ExtractionError, ExtractionSchemaError
from discovery.extraction.replay_client import ReplayExtractionClient

__all__ = [
    "AnthropicExtractionClient",
    "CopilotCliExtractionClient",
    "ExtractionClient",
    "ExtractionError",
    "ExtractionSchemaError",
    "ReplayExtractionClient",
]
