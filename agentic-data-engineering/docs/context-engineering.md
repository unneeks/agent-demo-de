# Context Engineering

## The problem

When an agent gets something wrong, the first useful question is rarely "was the
model bad?" — it is "what did it actually see?" If context is assembled by
concatenating whatever was nearby, that question has no answer.

Under the addendum there is a second question with the same shape: was the agent
shown the controls it is being judged against? An agent blamed for missing a
checklist item it was never given is being set up to fail.

## Model

| Type | Role |
|---|---|
| `ContextPolicy` | The rules: budget, admissible kinds, trust floor, staleness, citation requirement, redaction, per-kind caps, overflow strategy, **`require_delivery_context`** |
| `ContextItem` | One candidate: kind, priority, trust, freshness, tokens, source, provenance, **`pinned`** |
| `ContextBundle` | The immutable result: ordered items, drops **with reasons**, tokens used, `bundle_hash`, contract served |
| `Memory` | Durable state scoped `run` / `task` / `project` / `agent` / `organization` |

## Assembly

```
candidates
    ├─ delivery-control kinds pinned when the policy requires them
    ├─ kind not admissible      → KIND_NOT_ALLOWED
    ├─ below trust floor        → BELOW_TRUST_FLOOR
    ├─ older than max_age_days  → STALE
    ├─ not citable              → MISSING_CITATION
    ├─ redaction applied        (content rewritten, tokens re-estimated)
    └─ duplicate content        → DUPLICATE
    ▼
rank by (pinned, priority ↓, kind priority ↓, trust ↓, freshness ↓, id ↑)
    ├─ over per-kind cap        → KIND_NOT_ALLOWED   (pinned items exempt)
    ▼
greedy fill against usable_tokens = max_tokens − reserved_tokens
    └─ does not fit             → BUDGET_EXCEEDED    (pinned items raise instead)
    ▼
ContextBundle + bundle_hash
```

**Filters run before ranking.** A top-priority item that fails the trust floor is
reported as untrusted, not as crowded out — the difference matters when someone
is debugging why an agent missed something.

## The five guarantees

Each is a test in `tests/unit/test_context.py`.

### 1. Deterministic

Same policy version and candidates, in any order, produce a byte-identical
bundle. The sort key uses only explicit item properties with `id` as a final
tiebreak. The hash covers the policy identity and version, the budget, and the
ordered item identities *including content hashes* — so editing content changes
the hash even when the selection does not.

### 2. Budget-respecting

`tokens_used` never exceeds `usable_tokens`. Overflow is a declared decision:
`DROP_LOWEST_PRIORITY` (default), `TRUNCATE_LOWEST_PRIORITY`, or `FAIL`. The
`ContextBundle` entity independently rejects an over-budget bundle, so a
hand-built one cannot bypass the rule.

### 3. Accountable

Every candidate is in `items` or in `dropped` with a `DropReason`.
`bundle.manifest()` is the record attached to a `Decision`.

### 4. Citable

With `require_citation`, an item with neither `source_ref` nor
`content_reference` is refused. Uncited context cannot be cited in a decision.

### 5. Delivery-aware

With `require_delivery_context`, items of kind `DELIVERY_STANDARD`, `CHECKLIST`,
`ACCEPTANCE_CRITERION`, `GATE_RULE` or `DELIVERY_TEMPLATE` are pinned: they rank
first, are exempt from per-kind caps, and cannot be evicted by the budget.

If the pinned set cannot fit, the assembler raises `DeliveryContextError` rather
than dropping them. Failing loudly is better than running an agent that will be
judged against controls it never saw.

## Token estimation

Behind the `TokenEstimator` port. The default takes the larger of a character-
and a word-based estimate — no tokenizer dependency, and dense code is not
systematically underestimated.

Accuracy is explicitly not the goal. What it must be is **deterministic and
monotonic**: a `bundle_hash` that changed because a tokenizer was upgraded would
be worse than one from a crude but stable estimate. A real tokenizer drops in at
the port with no assembler change.

## Memory scopes

The scope is the control. `run`-scoped memory dies with the run;
`organization`-scoped memory is effectively a knowledge asset. Anything project-
or organization-scoped with `writeback_policy="automatic"` must declare
`retention_days` — unbounded shared memory has no review horizon.

## Worked example

```python
policy = ContextPolicy(
    ..., policy_key="ldm-execution", version="1.0.0",
    max_tokens=8000, reserved_tokens=2000,
    kind_priorities={ContextItemKind.CHECKLIST: 10, ContextItemKind.CODE: 3},
    minimum_trust=TrustLevel.MEDIUM, max_age_days=90,
    require_citation=True, require_delivery_context=True,
    redact_patterns=[r"sk-[A-Za-z0-9]+"],
)

bundle = assemble(policy, candidates,
                  agent_ref=agent.ref(pinned=True),
                  contract_ref=contract.ref(pinned=True))

decision = Decision(..., context_bundle_ref=..., contract_ref=...,
                    gate_readiness=readiness.scores(),
                    component_versions={"context_policy": "1.0.0", ...})
```

The decision now names the exact rules, the exact context, the contract it was
working under and the readiness it saw — which is what reproducibility
(criterion #19) requires.

## Scope

Phase 1 delivers the model and the assembler. Retrieval — deciding which
candidates exist at all — is a later phase. The seam is deliberate: assembly is
deterministic and testable now, and retrieval quality can later be evaluated
against a fixed assembler rather than a moving target.
