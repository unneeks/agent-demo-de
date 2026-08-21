"""Candidate content synthesis -- the one step in Marketplace Foundry that
calls an LLM.

Reuses ``discovery.extraction.client.ExtractionClient`` (the Protocol) and
its two live backends, ``AnthropicExtractionClient``/
``CopilotCliExtractionClient``, unmodified -- both are fully generic
"prompt + JSON Schema in, structured dict out" adapters with no
file-or-discovery-specific logic (ADR-0013), exactly the shape this needs.
``ReplaySynthesisClient`` (this package) is the one new piece: a hermetic
backend for tests, since discovery's own replay client's fixture lookup is
keyed on a "File: ..." line Foundry's prompts don't have.
"""
