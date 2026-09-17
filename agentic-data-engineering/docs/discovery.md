# Discovery — Uniform Agent-Based Extraction

Phase 1 built the metamodel; Phase 2 built `ProjectGraphService`, the one
sanctioned write path (`ingest_entity`/`ingest_relationship`) — but nothing had
ever produced a fact for it to ingest. Phase 3 is the first adapter layer that
turns a real project into real graph state: `discovery.discover_project` walks
a repository, asks an agent to read each file it recognizes, and writes what
comes back through `ProjectGraphService`.

An earlier deterministic-parsing design (regex over dbt `ref()` calls,
word-boundary matching for Markdown `DESCRIBES` edges) was scoped, verified
against the real target project, and then rejected: realistic discovery
targets include SQL, Terraform, CI/CD pipelines and free-form documents
describing current state, and pattern-matching does not generalize past
narrow, well-known formats like dbt's `ref()` syntax. Discovery is **uniform,
agent-based extraction for every source kind — with no per-source-type parser
and no dbt special-casing**, including for the seed-CSV content a deterministic
`csv.reader` could have handled exactly. See [ADR-0013](adr/0013-agent-based-extraction.md)
for the full reasoning and the alternatives rejected.

## The one idea that must not be compromised

**Every fact — however it was produced — still goes through exactly one door:
`ProjectGraphService.ingest_entity`/`ingest_relationship`.** The extraction
subsystem produces the same entity/relationship shapes any adapter would; it
just produces them by asking an agent to read a file and return structured
JSON, instead of by regex. Registry validation, dual-plane consistency, and
`Provenanced`'s confidence-mandatory-on-`INFERRED` rule apply identically
regardless of which mechanism produced the write — if anything they matter
more here, since an LLM's output is the least trustworthy input source in the
whole pipeline.

## The four-pass pipeline

```
discover_project(service, registry, project, client, repository_root=...)

  register_project(project)
        │
        ▼
  ┌─────────────────────────┐   walk.py classifies every file by
  │ 1. Technical extraction │   name/extension/path -- mechanical
  │    one client.extract() │   enumeration, never content-aware.
  │    call per technical   │   Each call returns entities plus
  │    candidate file       │   relationship candidates naming a
  └───────────┬─────────────┘   *symbolic* target (the file that
              │                 defines it may not be extracted yet).
              ▼
  ┌─────────────────────────┐
  │ 2. Deterministic         │   resolve.py: build {(type, id) -> ref}
  │    resolution            │   from every entity pass 1 produced,
  │    (discovery/resolve.py)│   resolve every symbolic candidate
  └───────────┬─────────────┘   against it. Unresolved -> DiscoverySkip,
              │                 never fabricated.
              ▼
  ┌─────────────────────────┐
  │ 3. Delivery extraction  │   one call per Markdown file, given the
  │    (Markdown files)     │   resolved technical-entity index. The
  └───────────┬─────────────┘   agent echoes a *known id* for DESCRIBES
              │                 targets, not a name to match later --
              │                 already resolved when parsed.
              ▼
  ┌─────────────────────────┐
  │ 4. Ingestion             │   entities, then resolved relationships
  │    (ProjectGraphService) │   (technical + delivery + the walk's own
  └─────────────────────────┘   structural CONTAINS edges), through the
                                 one sanctioned write path.
```

`discovery/walk.py` stays deterministic: walking a directory tree, applying a
denylist (`.git`, `__pycache__`, `target`, `dbt_packages`, `node_modules`,
`.venv`), and classifying a file by name/extension/path is mechanical
enumeration, not interpretation — it never opens a file and reasons about its
content. `discovery/resolve.py` also stays deterministic: it is bookkeeping
over strings the agent already produced, not a second reading of file content.
Everything downstream of "here is a file's raw bytes" is agent-judged,
uniformly, through one `extract()` call shape.

## Source-kind → entity-type dispatch table

`discovery/extraction/prompts.py`'s `SOURCE_KIND_ENTITY_TYPES` is the one
place a new source kind gets wired up — a walk-classifier entry plus a
schema-selection entry, not a new parser module:

| `source_kind` | Legal target entity types | Notes |
|---|---|---|
| `sql` | `Pipeline`, `DataAsset` | No `CodeArtifact` — `Pipeline.source_path` already captures the location, and `CONTAINS` has no legal `Pipeline`-as-source edge (see below) |
| `csv` | `DataAsset`, `SchemaDefinition` | Header/type inference goes through the agent, not `csv.reader` + sniffing — the closest call in this design, decided for uniformity |
| `dockerfile` | `Infrastructure` (`infrastructure_kind="container_image"`) | |
| `compose` | `Infrastructure` (`infrastructure_kind="compose_service"`), one per service | |
| `ci_workflow` | `Pipeline` (`pipeline_kind="ci_workflow"`) | Not `Workflow` — that entity is role/task orchestration, not a CI/CD concept |
| `terraform` | `Infrastructure` (`infrastructure_kind="terraform_module"`) | |
| `yaml_config` | *(none)* | `dbt_project.yml`/`profiles.yml` are walked and classified, then deliberately skipped — recorded as `DiscoverySkip(kind="no_target_entity_type")`, never sent to the agent |
| `markdown` | `DeliveryArtifact`, plus `DESCRIBES` edges to anything in `DESCRIBES_LEGAL_TARGET_TYPES` | Handled by pass 3, not pass 1 — needs the technical-entity index |

`DESCRIBES_LEGAL_TARGET_TYPES` = `Pipeline`, `DataAsset`, `ArchitectureElement`,
`Infrastructure`, `CodeArtifact` (checked against
`metamodel-registry/relationship_types.yaml`'s `DESCRIBES` entry). `Repository`
and `Project` are deliberately excluded — not legal `DESCRIBES` targets.

## Extraction schema derivation

Not the raw `schemas/*.schema.json` — those are published validation targets
for external consumers and include bookkeeping fields (`id`, `version`,
`created_at`, `provenance`, `discovered_by`, …) that must never be
model-generated. `content_schema_for()` mechanically subtracts the known
base-class fields (`MetamodelEntity`/`ProvenancedEntity`) and every
`EntityRef`-shaped field from an entity's full schema, then adds
`confidence: number` as a required field on every entity and relationship
candidate. This subtraction is deterministic code, not a hand-maintained
per-entity-type allowlist — a new entity type picks up correct extraction
schema derivation for free.

`source_document` is always platform-assigned from the walked file's relative
path, never model-generated. `id` assignment is likewise platform-controlled
(the agent's validated `suggested_id`), so re-running discovery against an
unchanged file upserts rather than duplicates.

## Confidence clamping

Every entity/relationship candidate must self-report `confidence`;
`parse_response.py` clamps it into `[MIN_CONFIDENCE, MAX_CONFIDENCE] = [0.05,
0.90]` before it ever reaches a `Provenanced` model. These are named module
constants, explicitly an initial estimate needing real calibration once live
extraction accumulates a track record.

The `0.90` ceiling matters structurally, not just as a convention:
`ProvenanceState.OBSERVED` facts require confidence exactly `1.0` (`Provenanced`'s
own validators, `domain/metamodel/base.py`). Capping agent self-report below
`1.0` makes it structurally impossible for a hallucinating model's stated
certainty to be mistaken for a directly-observed fact — the actual risk this
pipeline guards against. Every produced entity carries
`provenance=INFERRED`, `extraction_method=SEMANTIC_EXTRACTION`,
`discovered_by="agent-extraction@0.1.0"` — one uniform discoverer string for
every source kind, deliberately not suffixed per source type, since
`source_document` already carries that specificity.

## The `ExtractionClient` Protocol and its backends

```python
class ExtractionClient(Protocol):
    def extract(self, *, prompt: str, response_schema: dict) -> dict: ...
```

Three implementations behind the same Protocol:

- **`AnthropicExtractionClient`** — calls the real Anthropic Messages API with
  tool-use forced to a single tool whose `input_schema` is the response
  schema. Requires `pip install -e ".[agent]"` and `ANTHROPIC_API_KEY`.
- **`CopilotCliExtractionClient`** — shells out to the GitHub Copilot CLI
  (`copilot`/`gh copilot`) as a subprocess. A larger, differently-shaped risk
  than the Anthropic client: Copilot CLI is an interactive
  suggestion/explanation tool, not a schema-constrained structured-output API,
  so there is no guarantee it reliably returns conforming JSON. A response
  that doesn't parse cleanly fails the same safe way a malformed Anthropic
  response does — `parse_response.py` never partially trusts either backend's
  output.
- **`ReplayExtractionClient`** — golden-fixture-backed, hermetic. Given
  `(prompt, response_schema)`, computes a request hash, loads the matching
  fixture by path-slug, and raises `DiscoveryError` on a hash mismatch rather
  than silently replaying a stale answer. Every hermetic discovery test uses
  this backend.

## Golden-fixture recording

`scripts/record_extraction_fixtures.py` is a manual dev tool, never invoked by
pytest. It calls `AnthropicExtractionClient` once per file in a fixed manifest
— the real sibling project's dbt models, seeds, `Dockerfile`,
`docker-compose.yml`, `README.md`, plus synthetic Terraform/CI-YAML fixtures —
and writes one JSON file per input to `tests/fixtures/discovery/golden/`,
human-navigable and diff-reviewable in a PR. Regeneration is a deliberate,
reviewed act:

```bash
export ANTHROPIC_API_KEY=...
python scripts/record_extraction_fixtures.py
```

**Proving replay faithfully represents live is weaker here than ADR-0007's
contract-suite proof, stated honestly rather than oversold.** A database
adapter's output for a given input is deterministic and can be asserted
byte-equal to a reference; an LLM's is not, even at low temperature. The proof
this design offers is two-tiered instead: (1) static `Protocol` conformance
(`tests/unit/test_extraction_ports.py`) for all three clients, hermetic,
catching interface drift; (2) the live integration tests assert *structural*
properties against the same real files the golden fixtures were recorded from
(expected entity types present, counts in a documented range, zero partial
`IngestionError`s) rather than exact equality to the golden JSON.

## Errors and skips

| Kind | Where | Meaning |
|---|---|---|
| `DiscoverySkip(kind="no_target_entity_type")` | pass 1 | A classified file's `source_kind` has no legal target entity type today (`yaml_config`) |
| `DiscoverySkip(kind="unreadable_file")` | pass 1/3 | File could not be decoded as UTF-8 |
| `DiscoverySkip(kind="unresolved_relationship_target")` | pass 2 | A symbolic technical relationship candidate did not resolve against any entity extracted this run — including a `target_kind` mismatch, never force-matched by name alone |
| `DiscoveryFailure(kind="schema_violation")` | `parse_response.py` | The raw response failed `jsonschema.validate` against the schema the client was asked to conform to — the whole response is rejected |
| `DiscoveryFailure(kind="duplicate_suggested_id")` | `parse_response.py` | Two entities in one response claimed the same `suggested_id` — only the first is kept |
| `DiscoveryFailure(kind="entity_construction_failed")` | `parse_response.py` | A schema-conforming item still failed Pydantic construction (a metamodel invariant `jsonschema` doesn't itself enforce) |
| `DiscoveryFailure(kind="unknown_relationship_source")` | `parse_response.py` | A relationship's `source_local_id` didn't match any entity constructed from the same response |
| `DiscoveryFailure(kind="unknown_describes_target")` | `parse_response.py` | A `DESCRIBES` `target_id` wasn't in the known-entities index the client was given — checked again even though the schema already constrains it, because a client is never trusted to have actually enforced its own schema |
| `DiscoveryFailure(kind="ingest_entity_failed" / "ingest_relationship_failed")` | `orchestrate.py` | `ProjectGraphService` rejected the write (registry validation, provenance rules) |
| `DiscoveryFailure(kind="skipped_dangling_relationship")` | `orchestrate.py` | A relationship's endpoint was never successfully ingested this run |

`on_error="collect"` (the default) records a failure and continues — a single
file's bad output should not discard every other file's good writes.
`on_error="fail_fast"` re-raises the underlying error immediately instead.

## What this is not

- **No execution** of dbt, DuckDB, or Terraform — static file content only,
  handed to the agent as text.
- **No live network call** in the default `pytest tests/unit -q` run — every
  hermetic test uses `ReplayExtractionClient` against committed fixtures.
- **No PDF/DOCX** in this pass — Markdown only for delivery-document
  discovery.
- **No multi-turn agentic tool-use loop** — one file in, one structured
  response out. The deterministic walk decides what the agent sees; it does
  not browse the repository itself.
- **No automatic golden-fixture regeneration** — a manual, reviewed,
  explicitly-invoked script, never run by pytest.
- **Terraform and CI/CD are proven only via synthetic fixtures.** The real
  sibling project (`agentic-ai-ollama-demo/`) has no Terraform or CI/CD files
  today, so those two source kinds' golden fixtures
  (`tests/fixtures/discovery/golden/terraform__main.tf.json`,
  `ci__.github__workflows__ci.yml.json`) are hand-authored against synthetic
  input under `tests/fixtures/discovery/synthetic/`, not recorded from a live
  call against real project content. Stated plainly, not papered over — the
  same honesty standard ADR-0007 already applied to the unexecuted Neo4j
  adapter.
- **No `DataProfile` generation** — needs live profiling, out of scope here.
