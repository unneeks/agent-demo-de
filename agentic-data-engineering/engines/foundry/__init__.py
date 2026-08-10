"""Marketplace Foundry's pure engines: mining, pattern discovery, candidate
completeness scoring, and candidate lifecycle gating.

No I/O, no ``ProjectGraphService``, no LLM -- matching every other engine
in ``engines/``. Candidate *content* synthesis (the one step that calls an
LLM) lives in ``foundry/synthesis/`` instead, since it is I/O by
definition. See ``docs/marketplace-foundry.md`` and ADR-0022.
"""
