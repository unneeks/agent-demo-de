"""Deterministic engines that compute against the metamodel.

None of these call an LLM. Context assembly, gate readiness, impact analysis and
traceability are all pure functions of the graph and the registries, which is
what makes them testable in isolation and replayable after the fact.
"""
