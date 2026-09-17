"""Traceability chain resolution.

The §11 and §27 chain, walked end to end::

    Requirement → DeliveryTask → Agent → DeliveryArtifact → Test → Evidence
                → Approval → Deployment

The interesting output is not a complete chain. It is a **broken** one: the
first missing link tells a reviewer exactly where a requirement stops being
demonstrable, which is the question an auditor asks and the one most
organizations answer with a spreadsheet.

Pure: a graph in, a chain out.
"""

from __future__ import annotations

from pydantic import Field

from domain.metamodel.base import EntityRef, MetamodelModel
from domain.metamodel.enums import EntityType
from domain.metamodel.relationships import TRACEABILITY_CHAIN
from persistence.ports import GraphRepository


class TraceLink(MetamodelModel):
    """One hop in a traceability chain."""

    edge_type: str
    expected_type: EntityType
    #: Everything found at this hop. More than one is normal -- a task produces
    #: several artifacts -- and none means the chain is broken here.
    found: list[EntityRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def is_satisfied(self) -> bool:
        return bool(self.found)


class TraceabilityChain(MetamodelModel):
    """A resolved chain from one starting entity."""

    start: EntityRef
    links: list[TraceLink] = Field(default_factory=list)
    #: Index of the first unsatisfied link, or None when the chain is complete.
    broken_at: int | None = None

    @property
    def is_complete(self) -> bool:
        return self.broken_at is None

    @property
    def completeness(self) -> float:
        """Fraction of the chain that resolved. Feeds the gate traceability score."""
        if not self.links:
            return 0.0
        satisfied = sum(1 for link in self.links if link.is_satisfied)
        return satisfied / len(self.links)

    @property
    def confidence(self) -> float:
        """Weakest link. A chain is only as trustworthy as its least certain hop."""
        return min((link.confidence for link in self.links if link.is_satisfied), default=0.0)

    def break_description(self) -> str | None:
        """Plain statement of where the chain stops, for a reviewer."""
        if self.broken_at is None:
            return None
        link = self.links[self.broken_at]
        previous = (
            self.links[self.broken_at - 1].found[0]
            if self.broken_at > 0 and self.links[self.broken_at - 1].found
            else self.start
        )
        return (
            f"chain breaks after {previous}: no {link.expected_type.value} reachable "
            f"via {link.edge_type}"
        )

    def render(self) -> str:
        lines = [f"{self.start}"]
        for index, link in enumerate(self.links):
            marker = "->" if link.is_satisfied else "X "
            found = ", ".join(str(r) for r in link.found) if link.found else "(missing)"
            lines.append(f"  {marker} [{link.edge_type}] {found}")
            if self.broken_at == index:
                break
        lines.append(
            f"  completeness {self.completeness:.0%}"
            + ("" if self.is_complete else f" -- {self.break_description()}")
        )
        return "\n".join(lines)


def trace(
    start: EntityRef,
    graph: GraphRepository,
    *,
    chain: tuple[tuple[str, EntityType], ...] = TRACEABILITY_CHAIN,
    stop_at_break: bool = True,
) -> TraceabilityChain:
    """Follow the traceability chain from ``start``.

    ``stop_at_break=False`` continues past a missing link by re-seeding from the
    last resolved frontier, which is useful for reporting how much of the chain
    exists in fragments. The default stops, because past the first break the
    downstream links are no longer *this* requirement's evidence.
    """
    links: list[TraceLink] = []
    frontier: list[EntityRef] = [start]
    broken_at: int | None = None

    for index, (edge_type, expected_type) in enumerate(chain):
        found: dict[str, EntityRef] = {}
        confidence = 1.0

        for node in frontier:
            for rel in graph.relationships(source=node, type_=edge_type):
                if rel.target.type is not expected_type:
                    continue
                found[str(rel.target.identity)] = rel.target.identity
                if rel.confidence is not None:
                    confidence = min(confidence, rel.confidence)

        link = TraceLink(
            edge_type=edge_type,
            expected_type=expected_type,
            found=[found[k] for k in sorted(found)],
            confidence=confidence if found else 0.0,
        )
        links.append(link)

        if not link.is_satisfied:
            if broken_at is None:
                broken_at = index
            if stop_at_break:
                # Record the remaining links as unsatisfied so completeness
                # reflects the whole chain rather than only the part walked.
                links.extend(
                    TraceLink(edge_type=e, expected_type=t, found=[], confidence=0.0)
                    for e, t in chain[index + 1 :]
                )
                break
            continue

        frontier = link.found

    return TraceabilityChain(start=start, links=links, broken_at=broken_at)


def traceability_score(
    starts: list[EntityRef],
    graph: GraphRepository,
    *,
    chain: tuple[tuple[str, EntityType], ...] = TRACEABILITY_CHAIN,
) -> float:
    """Mean completeness across several starting points.

    This is what feeds ``GateState.traceability``. Averaging chains rather than
    counting complete ones matters: a gate should be able to tell the difference
    between "one requirement is entirely untraceable" and "every requirement is
    traceable but none has reached deployment yet".
    """
    if not starts:
        return 1.0
    return sum(trace(s, graph, chain=chain).completeness for s in starts) / len(starts)
