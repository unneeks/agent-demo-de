# Metamodel Specification

**Version 0.1.0.** The authoritative machine-readable form is [`schemas/`](../schemas/);
this document explains intent and the rules schemas cannot express.

## Source of truth

| Half | Lives in | Changing it |
|---|---|---|
| Entity **shapes** — fields, types, validators | Pydantic models in `domain/metamodel/` | code change + regenerate schemas |
| **Vocabularies** — capabilities, the role chain, relationships, bindings, approvals, whole delivery models | YAML in `metamodel-registry/` | data change, validated at load |

Tests enforce that the halves agree: `METAMODEL_VERSION` must equal the registry
version, every role's capabilities must exist, every relationship endpoint must
be a real entity type, every delivery task's checklist must exist. See ADR-0002.

## Common structure

```
Identified        id · name · description · entity_type · twin
Versioned         version · metamodel_version · created_at · updated_at
Provenanced       provenance · confidence · evidence_refs · discovered_by
                  source_document · source_section · extraction_method
Blockable         blocking (refused unless provenance is verified)
MetamodelEntity   = Identified + Versioned + labels + attributes
ProvenancedEntity = MetamodelEntity + Provenanced
```

**Identity.** Catalog entities use slug + semver so a component can be pinned and
reproduced. Instance entities (Evidence, Event, Decision, Approval, Change) use
ULIDs — time-sortable, because they are created in volume and read in time order.

**References.** All cross-entity links go through `EntityRef {type, id, version}`,
serialized as `Type:id@version`. `ref.identity` strips the version — that is what
the graph plane keys on.

**Twin.** Every entity declares `TECHNICAL`, `DELIVERY` or `SHARED`. Navigation
and reporting, not a partition: both live in one graph and one store.

## Provenance

| State | Meaning | Required | May block | May automate |
|---|---|---|---|---|
| `OBSERVED` | Read directly from a source | `discovered_by`; confidence 1.0 | yes | yes |
| `INFERRED` | Concluded, not seen | **`confidence`** | **no** | no |
| `HUMAN_VERIFIED` | A named human checked it | `human_verified_by` + timestamp | yes | yes |
| `CERTIFIED` | Verified *and* passed a formal gate | `human_verified_by` + timestamp | yes | yes, incl. high risk |

Enforced by the `Provenanced` validator, by the `Blockable` mixin for the
blocking column, and again by `CHECK` constraints in PostgreSQL.

`SEMANTIC_EXTRACTION` additionally requires `source_document`: an unattributable
reading of a document cannot be checked by a human.

## Entities by group

### Technical twin — `entities/technical/`
`Project` · `Repository` · `CodeArtifact` · `Pipeline` · `DataAsset` ·
`SchemaDefinition` · `DataProfile` · `Infrastructure` · `CloudResource` ·
`ArchitectureElement` · `Test` · `Incident` · `Change` · `Deployment`

All `ProvenancedEntity`. `DataAsset` covers dataset/table/view/topic/file/column/
data-product via `asset_kind` and a self-nesting `parent_ref`; `Dependency` and
`Lineage` are relationship types, not entities (ADR-0010). `DataProfile` is kept
separate from `DataAsset` for the same reason `SchemaDefinition` is — profiling
drift is a first-class, comparable fact, not an overwritten value (ADR-0012).

### Delivery twin — `entities/delivery/`
See [`delivery-model.md`](delivery-model.md).

### Organization — `entities/organization/`
`DeliveryRole` · `EngineeringResponsibility` · `EngineeringRole` · `Agent` ·
`Skill` · `Tool` · `KnowledgePack` · `Policy`

`Agent` carries a `DeliveryCapabilityDeclaration` (§13) — supported phases,
tasks, checklists, artifact kinds and gates — so it claims organizational work,
not just capability.

**Agent lifecycle**, with illegal transitions refused:

```
DRAFT → CANDIDATE → EVALUATED → CERTIFIED → DEPLOYED → MONITORED
                        ▲                                  │
                        └────── REEVALUATION_REQUIRED ◀─────┘
                                        │
                                  DEPRECATED → RETIRED
```

**Action classes**, required on every action, no default:

| Class | Example | Reversible |
|---|---|---|
| `READ_ONLY` | read metadata | yes |
| `LOW_RISK_WRITE` | create branch, open PR | yes |
| `HIGH_RISK_WRITE` | merge code, alter schema | no |
| `DESTRUCTIVE` | drop table, change access control | no |

The last two cannot be constructed with `minimum_approval=NONE`.

### Capability — `entities/shared/capability.py`
`Problem` · `Requirement` · `Capability` · `DeliveryCapability` · `CapabilityGap`

Two capability kinds as distinct entities, not one with a flag: they are
discovered from different evidence (code versus documentation), and a project
routinely scores high on one and low on the other — which is the most valuable
finding the platform produces. `CapabilityGap` is shared and references either.

### Evaluation — `entities/evaluation/`
`EvaluationSuite` · `EvaluationScenario` · `EvaluationMetric` · `Evaluation` ·
`MetricResult` · `Evidence` · `Finding`

Metrics carry a `dimension` of `technical` or `delivery`, and
`Evaluation.trust_score` is the **minimum** of the two rather than a weighted
average — averaging would let a 98% technical score paper over a 40% conformance
score, which is what §28 forbids.

### Work — `entities/shared/work.py`
`Workflow` · `Task` · `Artifact` · `Event` · `Decision` · `Observation`

`Task` is one *execution*; `DeliveryTask` is the organization's template.
`Decision` stores a concise auditable summary plus evidence, the context bundle,
the contract and pinned component versions — never raw chain-of-thought.

## Relationships

Edges are objects with their own provenance (ADR-0004). The natural key is
`(source, type, target)` on identity refs. 64 types across four dimensions:

| Dimension | Count | Examples |
|---|---|---|
| `TECHNICAL` | 18 | `DEPENDS_ON`, `COVERS`, `HAS_SCHEMA`, `IMPLEMENTS`, `PROFILES` |
| `DELIVERY` | 21 | `HAS_PHASE`, `VALIDATED_BY`, `ENDS_AT_GATE`, `REQUIRES_EVIDENCE` |
| `CROSS` | 19 | `GOVERNS`, `DESCRIBES`, `TRIGGERS_TASK`, `TRACED_TO`, `SATISFIES` |
| `SHARED` | 6 | `EVALUATES`, `SUPPORTS`, `CITES`, `ASSEMBLED_FROM` |

`requires_provenance: false` marks structural configuration; `true` marks
discovered claims. Validation is a separate step so an edge written under an
older registry version can still be deserialized and inspected.

## Versioning

Semver applied to a schema: **patch** for documentation, **minor** for additive
and backward-compatible changes, **major** for breaking ones. A reader can
interpret any record with the same major version whose minor version is not
ahead of its own.

## Extending the metamodel

| To add | Do this |
|---|---|
| A capability (either kind) | Append to the relevant `*_capabilities.yaml`. |
| A responsibility, engineering role or delivery role | Append to its registry. |
| A relationship type | Append to `relationship_types.yaml` with its endpoints. |
| A delivery process kind | Append to `risk.yaml`. |
| A whole delivery model | Add a file under `delivery-models/`. |
| A field on an entity | Edit the model, bump the minor version, run `export_schemas.py`. |
| An entity type | Add to `EntityType`, create the model, register it in `entities/__init__.py`. |

The last two are code changes and are meant to feel heavier than the rest.
