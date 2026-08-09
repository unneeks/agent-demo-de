# ADR-0005: Capability / Platform / TechnologyBinding indirection

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 1

## Context

The fastest way to build a data engineering agent is to write it against the
stack in front of you. It works immediately and welds the agent to one cloud —
even though the agent's *reasoning* ("changes to a streaming source need
reconciliation testing") was never cloud-specific.

## Decision

```
Requirement → Capability → TechnologyBinding → Technology
              (agents           (adapters
               reason here)      resolve here)
```

Agent and skill logic may reference capability keys; it may not reference
technologies. `platforms.yaml` is the only file in the metamodel permitted to
name a cloud service. A `neutral` platform covers genuinely portable
technologies and is included in every platform's resolution.

The addendum adds a second, parallel catalog: `DeliveryCapability`
(Change Assurance, Release Assurance, Operational Readiness…). Kept as a distinct
entity rather than a flag on `Capability`, because the two are discovered from
different evidence and a project routinely scores high on one and low on the
other — which is the most useful finding the platform produces.

## Consequences

**Good.** The same logical solution moves between clouds by changing bindings.
Adding Azure is a YAML addition. Gap analysis operates on capabilities and is
cloud-independent by construction. Delivery capability is inferred from what the
gates actually enforce, not from what the handbook asserts.

**Costs.** An extra hop. The binding table needs maintaining. `detection_hints`
are heuristics — which is why anything derived from them is `INFERRED`.

**Enforcement.** Partly social: nothing stops a future agent importing a BigQuery
client. The structural defences are that the domain layer has no cloud
dependencies and the portability tests assert no leakage between platforms. A
lint rule forbidding vendor imports in `domain/` would be a reasonable addition.

## Alternatives rejected

**Direct technology references.** Faster; permanently single-cloud.

**One capability entity with a kind flag.** Would let a technical capability
satisfy a delivery requirement by accident.
