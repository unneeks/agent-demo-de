# ADR-0009: Four-level role chain, and inferred rules that cannot block

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 1

Two decisions that share a theme: keeping human accountability distinguishable
from machine capability.

## Part 1 — the role chain

### Context

The addendum draws:

```
Delivery Role → Engineering Responsibility → Engineering Role → Agent
```

but lists no `EngineeringResponsibility` among its entities, leaving open
whether the middle is an entity, an edge, or a field.

The distinction being drawn is real. "Data Architect" appears in the RACI, signs
the architecture gate and exists whether or not this platform does. "Data
Architect" is *also* a marketplace abstraction an agent implements and an
evaluation certifies. They are frequently named the same and are frequently not
the same: one delivery role usually carries several responsibilities, and one
responsibility is often shared across delivery roles.

### Decision

`EngineeringResponsibility` is a first-class entity. Delivery roles are
`ACCOUNTABLE_FOR` responsibilities; responsibilities are `FULFILLED_BY`
engineering roles; engineering roles are `IMPLEMENTED_BY` agents.

Responsibilities carry `delegable_to_agent`. Some accountability is not
delegable regardless of agent quality — `resp.architecture-signoff`,
`resp.security-clearance`, `resp.release-readiness` — and the registry validator
**rejects** any non-delegable responsibility that names an engineering role.

That rule caught a genuine error in the first draft of the registry: security
clearance and release readiness had been marked non-delegable while naming
engineering roles. The fix was to split each into a delegable *assessment* an
agent can perform and a non-delegable *sign-off* only a person can give — which
is the distinction the addendum is actually about.

### Consequences

**Good.** An organization can reshuffle job titles without invalidating the agent
ecosystem. Non-delegable accountability is machine-checkable. `resolve_role_chain()`
makes the whole chain queryable, and prints "(human only)" where no agent may go.

**Costs.** Four levels to traverse, and a third role-ish registry to maintain.
Contributors will initially put things in the wrong catalog.

### Alternatives rejected

**A `MAPS_TO` edge with attributes.** Three levels, fewer entities, but a
responsibility cannot be reasoned about or evaluated on its own.

**Reusing the `responsibilities` string list on `EngineeringRole`.** Simplest, and
loses exactly the distinction being drawn.

## Part 2 — inferred rules cannot block

### Context

The addendum states that inferred information must never silently become
certified organizational policy. Left as guidance, this fails the test it sets
itself: *can an agent violate the rule by accident?* Yes — an extraction
pipeline producing a thousand rules from a handbook will mark some of them
blocking unless something stops it.

### Decision

A `Blockable` mixin on `Standard`, `Control`, `ApprovalRule`, `ChecklistItem` and
`ApprovalGate`. Its validator refuses `blocking=True` when provenance is
`INFERRED`. `provenance.yaml` carries the same fact as `may_block`, and the
registry validator refuses a registry that permits inferred blocking.

The intended workflow: extract as advisory with a citation, have a human read
the cited paragraph, promote to `HUMAN_VERIFIED`, and only then does it block.

### Consequences

**Good.** A misread paragraph cannot halt delivery. Extracted rules still provide
value as advisory signals. The promotion path is explicit and testable.

**Costs.** An assimilated delivery model is inert until someone reviews it, which
is real adoption friction — and the correct trade. A platform that blocks
releases on a hallucinated rule gets switched off once and never switched back on.
