# ADR-0006: Context assembly is a deterministic, delivery-aware function

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 1

## Context

Context assembly is usually incidental: retrieve, concatenate, truncate, send.
That makes three things impossible — reproducing a decision, debugging a wrong
answer, and governing what an agent may see. Truncation is the worst part: it
discards the tail and records nothing.

The addendum adds a fourth failure. If an agent is judged against a checklist and
a gate, and those controls were silently evicted from its context by a budget,
the evaluation measures nothing.

## Decision

**Policy before selection.** `ContextPolicy` declares budget, admissible kinds,
trust floor, staleness, citation requirement, redaction, caps, overflow strategy
and `require_delivery_context` — versioned, so a bundle names the exact rules
that produced it.

**Assembly is pure and LLM-free.** Filter, rank by
`(pinned, priority, kind priority, trust, freshness, id)`, apply caps, greedy
fill. Filters run before ranking so a rejection reports the real reason.

**Exclusions are recorded** with a `DropReason`. Nothing vanishes silently.

**Bundles are content-addressed.** `bundle_hash` covers policy identity and
version, budget, and ordered item identities including content hashes.

**Delivery controls are pinned.** Under `require_delivery_context`, control items
rank first, are exempt from caps, and cannot be evicted. If they cannot fit,
`DeliveryContextError` is raised rather than dropping them.

**Token estimation is a port** with a deterministic heuristic default. Accuracy
is explicitly not the goal; a hash that changed because a tokenizer was upgraded
would be worse than one from a crude but stable estimate.

## Consequences

**Good.** A `Decision` referencing a bundle can be honestly replayed. Context
selection is unit-testable in milliseconds. `manifest()` gives a reviewer the
inputs without re-running anything. An agent can never be judged against
controls it was not shown.

**Costs.** Candidates must be materialized with priority, trust and freshness
before assembly, pushing work onto retrieval. Storing every bundle needs a
retention policy — though bundles hold references and hashes, not content.

**Failing loudly on unfittable controls** will occasionally block a run that
would otherwise have proceeded. That is the intended trade: a blocked run is
visible, a silently degraded evaluation is not.

## Alternatives rejected

**Concatenate and truncate.** Forecloses reproducibility, debuggability and
governance simultaneously.

**Model-assisted selection.** Non-deterministic, unauditable, untestable. If
wanted, it belongs in retrieval, with deterministic assembly still governing
admission.
