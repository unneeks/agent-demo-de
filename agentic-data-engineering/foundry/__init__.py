"""Marketplace Foundry orchestration: mine a project's already-ingested
graph for recurring engineering patterns, synthesize candidate Skills/
Tools/Agents from them (the one step that calls an LLM), evaluate their
structural completeness, and write everything through
``ProjectGraphService``.

Deliberately **not** wired into ``orchestrator/cycle.py``: this is invoked
independently, any time a caller wants to look for new marketplace
opportunities against a project graph that already exists --
``foundry/run.py::run_foundry_cycle()`` is its own entry point, the same
way ``discovery.orchestrate.discover_project`` is its own entry point
rather than a forced step in every cycle. See ``docs/marketplace-foundry.md``
and ADR-0022.
"""
