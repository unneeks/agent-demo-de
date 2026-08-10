# The Delivery Twin

## Why this exists

The original platform modelled the technical reality of a project: code,
pipelines, data assets, tests. That answers *what has been built*. It cannot
answer the question that actually governs whether a change ships:

> How does this organization deliver and govern changes to what has been built?

Without that, an agent can produce a technically perfect change that is
unmergeable — because nobody ran the checklist, the security assessment is
missing, the runbook was not updated, and the architect never signed.

The Delivery Twin models the organization's process as **structured, versioned,
executable metadata**. Not as reference material an LLM reads.

## The distinction that makes it executable

| Reference material | Executable metadata |
|---|---|
| "Architecture must be reviewed before development" in a wiki | `DeliveryPhase(entry_criteria=[...], depends_on=[architecture])` |
| A checklist as a bulleted list | `Checklist` with 12 `ChecklistItem`s, each with a `validation_method` |
| "The architect approves" | `ApprovalGate(required_roles=[data-architect])` with computed readiness |
| "Every entity needs an owner" | `AcceptanceCriterion(validation_method=METADATA_LOOKUP, blocking=True)` |

The right-hand column can be computed against. The left cannot.

## Entities

| Group | Entities |
|---|---|
| Model | `DeliveryModel` · `DeliveryPhase` · `DeliveryProcess` · `Methodology` |
| Work | `DeliveryTask` · `DeliveryActivity` · `DeliveryInput` · `DeliveryOutput` · `DeliveryArtifact` |
| Controls | `Checklist` · `ChecklistItem` · `AcceptanceCriterion` · `DefinitionOfDone` · `Standard` · `Control` |
| Gates | `ApprovalGate` · `ApprovalRule` · `Approval` · `EvidenceRequirement` |
| Binding | `DeliveryContract` |
| Org | `DeliveryRole` · `RaciAssignment` · `Template` |

Three modelling decisions worth stating (ADR-0010):

- **`DeliveryProcess` with a `process_kind`** replaces separate `ReleaseProcess`,
  `ChangeProcess` and `IncidentProcess` entities. They differ in trigger and
  gates, not in shape, and the kinds live in the registry so a new one is a data
  change.
- **`DeliveryInput`/`DeliveryOutput` are specifications, not instances.** "This
  task requires a Business Requirements document" is a durable statement about
  the process; the document that satisfies it on one project is a
  `DeliveryArtifact`. Conflating them makes "which required inputs are missing?"
  unanswerable.
- **No phases are assumed.** The nine phases in the worked model are registry
  data. A model with three phases or nineteen is equally representable.

## DeliveryContract — what agents execute against

A contract binds everything one task needs into one versioned object: inputs,
outputs, skills, tools, knowledge, policies, checklists, acceptance criteria,
evidence requirements and the gate it feeds.

Its most important method answers the question the original design could not
ask:

```python
contract.conformance_of(
    agent_key="copilot-agent",
    capabilities={"data-modelling"},
    skills={"logical-model-generation"},
    tools={"modeling-tool"},
)
# ContractConformance(
#   technically_capable=True,
#   delivery_conformant=False,
#   gaps=[checklist: logical-model-checklist (required),
#         gate: gate.data-architecture-review (required),
#         artifact: logical-data-model (required)])
```

Both dimensions are computed and reported separately, because the interesting
failure is an agent that passes the first and fails the second. A contract with
no controls is rejected at construction — otherwise every agent would satisfy it
vacuously.

## Checklists

Structured, with per-item validation methods so the platform knows what an agent
could discharge unattended:

```
logical-model-checklist   75% machine-evaluable (12 items)
architecture-checklist     0% machine-evaluable (4 items)
```

An architecture checklist that is 0% machine-evaluable is not a candidate for
automation however capable the agent, and saying so up front is more useful than
discovering it at run time.

**Item statuses:** `PASS` · `FAIL` · `NOT_APPLICABLE` · `WAIVED` · `PENDING`.

Three rules that look small and are not:

- **Unevaluated is PENDING, not passed.** Defaulting the other way is how
  checklists stop meaning anything.
- **`NOT_APPLICABLE` leaves the denominator; `WAIVED` stays in it.** A control
  that never applied should not depress the score; a control that applied and
  was waived should be visible in it.
- **An expired waiver stops counting.** Otherwise a temporary exception silently
  becomes permanent.

A waiver requires a reason, an approver, a timestamp and evidence. An
unattributed waiver is indistinguishable from a skipped control.

## Gates

A gate computes readiness across six dimensions and returns a status with
itemized blockers:

```
gate.data-architecture-review
  Artifacts        100% OK
  Checklists       100% OK
  Evaluations      100% OK
  Approvals        100% OK
  Evidence         100% OK
  Traceability      87% --
  Overall           97% -> CONDITIONAL
```

**Decision rule** — stated precisely so it is testable:

- any unmet **mandatory** requirement on a **blocking** gate → `BLOCKED`
- unmet advisory requirements only → `CONDITIONAL`
- everything met → `PASS`

A non-blocking gate can never report `BLOCKED`: an advisory gate that halts
delivery is not advisory.

The engine **computes**; it does not **decide**. `GateReadiness` is information
for a human; `Approval` is the human's decision. Conflating them would either
let the platform approve things or reduce it to a checklist nobody trusts. The
`Approval` records the readiness the approver saw, so a later reviewer can tell
whether the decision was well informed.

## Extraction and the blocking rule

Delivery metadata is largely read out of prose, so every entity carries
`source_document`, `source_section` and `extraction_method` alongside
provenance and confidence.

The addendum is explicit that inferred information must never silently become
certified organizational policy. That is enforced structurally by the
`Blockable` mixin:

> A `Standard`, `Control`, `ApprovalRule`, `ChecklistItem` or `ApprovalGate`
> with `INFERRED` provenance cannot be `blocking=True`.

The intended workflow is therefore:

```
extract → INFERRED, blocking=False, cites DeliveryHandbook.pdf#6.3   (advisory)
        → human reviews the cited paragraph
        → HUMAN_VERIFIED, blocking=True                              (enforced)
```

Without this, a misread paragraph halts delivery and the platform loses the
organization's trust permanently.

## Dual impact

`analyze_impact()` returns both dimensions, and delivery obligations inherit the
confidence of the graph path that produced them:

```
[artifact] logical-data-model-v3 -- may now be out of date (confidence 0.70)
```

0.70 because the `DESCRIBES` edge was inferred. Acting on that as certainty
means telling someone to update a document that was never about their code.

Risk escalates from the delivery side too: a one-line change that trips a
HIGH-risk gate is a HIGH-risk change, and only the delivery twin knows it.

## Traceability

```
Requirement → DeliveryTask → Agent → DeliveryArtifact → Test → Evidence
            → Approval → Deployment
```

The useful output is a *broken* chain. `trace()` reports where a requirement
stops being demonstrable:

```
Requirement:REQ-900
  -> [TRACED_TO] DeliveryTask:task.logical-data-model
  X  [PERFORMED_BY] (missing)
  completeness 14% -- chain breaks after DeliveryTask:task.logical-data-model:
                      no Agent reachable via PERFORMED_BY
```

`traceability_score()` averages completeness across requirements and feeds
`GateState.traceability`. Averaging chains rather than counting complete ones
lets a gate distinguish "one requirement is untraceable" from "every requirement
is traceable but none has deployed yet".

## The worked model

`metamodel-registry/delivery-models/data-engineering.yaml` is example
organizational data, not part of the metamodel. It exists so the engines are
tested against a realistic process, and so a reader can see what an assimilated
delivery model looks like. It is `HUMAN_VERIFIED` because it was written by hand
— which is also why its gates are permitted to block.
