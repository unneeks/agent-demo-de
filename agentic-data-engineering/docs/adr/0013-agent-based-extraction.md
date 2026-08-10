# ADR-0013: Agent-based extraction behind an `ExtractionClient` Protocol, uniformly across every source kind

**Status:** Accepted · **Date:** 2026-08-09 · **Phase:** 3

## Context

Phase 3 is the first adapter layer that turns a real project into real graph
state — discovery. An initial design scoped deterministic parsing: regex over
dbt `ref()` calls to resolve `DEPENDS_ON` edges between models, word-boundary
matching over Markdown to find `DESCRIBES` edges to known technical entities.
It was verified against the real target sibling project
(`agentic-ai-ollama-demo/`) and worked for that project's dbt models.

It was then explicitly rejected on review. Realistic discovery targets are not
limited to dbt SQL: Terraform, CI/CD YAML, Dockerfiles, docker-compose,
free-form Markdown describing current state, and "any data engineering
project" a customer might bring, not just projects that happen to use dbt's
particular `ref()` syntax. A regex-per-format design does not generalize past
the narrow set of formats it was written against, and every new source kind
would mean a new bespoke parser module.

## Decision

**Uniform, agent-based extraction for every source kind, with no per-source
deterministic parser and no dbt special-casing** — including for the
seed-CSV/schema content a deterministic `csv.reader` + type-sniffer could have
handled exactly. This supersedes the earlier deterministic design in full, not
incrementally.

**`ExtractionClient` is a `Protocol`** — a deliberate reversal from how the
per-source-type parser design would have been scoped. A dbt-lineage reading
and a Markdown reading take genuinely different inputs and are not
interchangeable implementations of one operation, so a Protocol over *them*
would document nothing a plain function signature doesn't already say (and
correctly, the superseded design did not introduce one). But a live
LLM-backed client and a golden-fixture-backed replay client for hermetic tests
*are* two interchangeable implementations of one operation — a prompt plus a
target schema go in, a dict comes out — exactly ADR-0007's "one interface,
multiple real backends" pattern. `ExtractionClient` earns a Protocol for that
reason: not "Protocols are good" as a default, but this specific swap point
earning one where a per-source parser correctly would not have.

**Two real backends prove the Protocol is earning its keep as genuine
interchangeability, not a Protocol with one implementation and an aspirational
second slot:**

- `AnthropicExtractionClient` — the real Anthropic Messages API,
  tool-use-forced structured output. Lazily imports `anthropic`, mirroring the
  existing lazy-import convention for `neo4j`/`psycopg` (ADR-0007).
- `CopilotCliExtractionClient` — shells out to the GitHub Copilot CLI
  (`copilot`/`gh copilot`) as a subprocess, per explicit request. This carries
  a materially different, larger risk than the Anthropic client, recorded here
  plainly rather than presenting both backends as equally proven: Copilot CLI
  is built as an interactive suggestion/explanation tool, not a
  schema-constrained structured-output API. There is no known guarantee it can
  be driven non-interactively to return JSON conforming to an arbitrary
  schema on the first try, or that any particular invocation flags exist on a
  given installed version. The adapter's job is to prompt for JSON, extract
  the JSON object from whatever prose surrounds it in the CLI's output, and
  hand the result to the same `parse_response.py` validation boundary the
  Anthropic client's output goes through — a response that doesn't parse
  cleanly fails the same safe way a wrong Anthropic field would.

**Confidence clamping structurally separates agent self-report from an
observed fact.** Every entity/relationship candidate must self-report
`confidence`; `parse_response.py` clamps it into `[0.05, 0.90]` before
constructing the real Pydantic model. `ProvenanceState.OBSERVED` requires
confidence exactly `1.0` (`Provenanced`'s own validators, unrelated to this
phase). Capping the agent's self-reported ceiling below `1.0` makes it
structurally impossible for a hallucinating model's stated certainty to be
mistaken for a directly-observed fact.

## Consequences

**Good.** One extraction pathway to maintain regardless of source kind.
Extending to a new source kind is a `discovery/walk.py` classifier entry plus
a `SOURCE_KIND_ENTITY_TYPES` schema-selection entry, not a new parser module.
Adding a third backend is one more adapter module behind the same Protocol,
with no change to `orchestrate.py`, `resolve.py`, or `parse_response.py`.

**Costs, stated honestly.** Replay-vs-live equivalence can only be proven
structurally, not exactly, because the underlying capability — an LLM reading
a file — is non-deterministic even at low temperature. This is weaker than
every other Protocol-backed component in this codebase: the contract suite
(ADR-0007) asserts real database adapters produce byte-identical results to
the in-memory reference for a given input; nothing analogous is possible here.
The two-tiered proof this phase offers instead — static Protocol conformance
plus structural assertions in a live integration test — is a genuine,
permanent, named limit, not a gap expected to close later.

Golden fixtures are single-sourced from the Anthropic backend (chosen because
it has an actual schema-constrained API, making it the more reliable source of
a stable "canonical" answer to replay). The Copilot CLI backend has no replay
coverage of its own — only its own live integration test, with the most
tolerant assertions in the suite, proving the adapter's parsing and
failure-handling path works end-to-end against whatever the CLI actually
returns, not that it reproduces any particular count.

**Known gap, in the same spirit as ADR-0007's unexecuted-Neo4j-adapter note.**
The exact Anthropic Messages API call shape (the tool-use/`tool_choice`
contract, the default model id, the SDK's exception hierarchy) and the exact
Copilot CLI invocation contract (non-interactive mode, exit codes,
stdout/stderr shape) could not be verified against live documentation or a
live installed CLI from the environment this was written in. Both are flagged
directly in their adapter modules' docstrings as best-effort placeholders that
must be checked against real docs/binaries before being trusted in
production — not silently assumed correct.

## Alternatives rejected

**The deterministic-per-source design** (regex over dbt `ref()`, word-boundary
Markdown matching) — the design that preceded this one. Rejected on review:
does not generalize past the narrow set of formats it was written against;
every new source kind needs a new bespoke parser.

**A hybrid design** — deterministic parsing for dbt/CSV (where it works
exactly), agent extraction for everything else. Rejected in favor of
uniformity: a hybrid reintroduces the same special-casing problem in
miniature, and the closest case for a deterministic exception (seed-CSV
header/type extraction) is explicitly decided against in `docs/discovery.md`.

**Mocking the LLM call in tests, instead of golden-fixture replay.** A mock
proves the orchestration code calls `extract()` correctly; it proves nothing
about whether real extraction output is shaped the way the rest of the
pipeline assumes. Golden fixtures, recorded from one real call and replayed
thereafter, keep the hermetic suite honest about what a real response actually
looks like.

**Recording golden fixtures from both backends.** Rejected as doubling
fixture-maintenance burden for two backends whose phrasing would differ
anyway even for the same input — the Anthropic recording is canonical, the
Copilot CLI backend is proven live instead.

**A single mega-prompt per project instead of per-file.** Rejected: per-file
extraction keeps each call's blast radius small, keeps golden fixtures
independently reviewable and replayable, and avoids a token-budget ceiling
that would only get worse as a project grows.
