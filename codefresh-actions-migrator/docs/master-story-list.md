# Codefresh to GitHub Actions Migrator - Master Story List

This backlog is organized so work can be assigned by epic, priority, and dependency. Owner, sprint, and status are intentionally left as planning fields in the spreadsheet version.

## Legend

- Priority: P0 = release blocker, P1 = core MVP, P2 = important follow-up, P3 = polish.
- Estimate: relative story points.
- Status: Backlog unless noted otherwise.

## Summary

| Epic | Stories | Points |
|---|---:|---:|
| Project Foundation | 5 | 13 |
| Deterministic Converter Core | 8 | 35 |
| GitHub Actions Generation | 5 | 23 |
| VS Code Extension UX | 6 | 29 |
| Copilot and AI Tooling | 5 | 24 |
| Knowledge and Learning | 3 | 13 |
| Testing and Quality | 6 | 23 |
| Packaging and Documentation | 4 | 13 |
| **Total** | **42** | **173** |

## Project Foundation

| ID | Priority | Estimate | Story | Acceptance Criteria | Dependencies |
|---|---|---:|---|---|---|
| CFM-001 | P0 | 2 | Scaffold standalone VS Code extension package under `codefresh-actions-migrator`. | Package has compile/test scripts, TypeScript config, VS Code extension manifest, and local README. | None |
| CFM-002 | P0 | 2 | Configure extension activation, commands, and contributed chat participant metadata. | Extension activates on migration commands and `@cfmigrator`; command palette entries are visible. | CFM-001 |
| CFM-003 | P1 | 3 | Define public migration domain interfaces. | `CodefreshPipeline`, `CodefreshStep`, `MigrationPlan`, `StepMapping`, and `KnowledgePattern` are exported and covered by compile-time checks. | CFM-001 |
| CFM-004 | P1 | 3 | Establish repository hygiene for generated artifacts. | `node_modules`, `out`, `.vscode-test`, and packaged VSIX files are ignored. | CFM-001 |
| CFM-005 | P2 | 3 | Add contribution/development guide for local extension development. | README explains install, compile, test, debug launch, and manual smoke-test workflow. | CFM-001 |

## Deterministic Converter Core

| ID | Priority | Estimate | Story | Acceptance Criteria | Dependencies |
|---|---|---:|---|---|---|
| CFM-006 | P0 | 3 | Scan workspaces for Codefresh pipeline files. | Scanner finds `codefresh.yml`, `codefresh.yaml`, and `.codefresh/*.yml` while skipping noisy folders. | CFM-003 |
| CFM-007 | P0 | 5 | Parse Codefresh YAML into a normalized pipeline model. | Parser validates YAML, extracts version, variables, and ordered steps, and reports parse errors clearly. | CFM-003 |
| CFM-008 | P0 | 3 | Normalize freestyle, build, push, composition, approval, deploy, and unknown steps. | Analyzer consistently extracts type, title, image, commands, env, `when`, and raw fields. | CFM-007 |
| CFM-009 | P0 | 5 | Map Codefresh git clone and freestyle steps to GitHub Actions. | Clone becomes `actions/checkout@v4`; freestyle becomes `run`; container/image behavior is warned or mapped. | CFM-008 |
| CFM-010 | P1 | 5 | Map Docker build and push patterns. | Build uses Buildx/build-push-action; push includes registry login, required secrets, and verification warnings. | CFM-008 |
| CFM-011 | P1 | 5 | Map composition and service patterns. | Representable services become job services; unsupported compose behavior becomes a guarded `docker compose` step with warnings. | CFM-008 |
| CFM-012 | P1 | 5 | Map approval and deploy patterns safely. | Approval maps to GitHub environment with reviewer warning; deploy commands are preserved or flagged for manual migration. | CFM-008 |
| CFM-013 | P1 | 4 | Handle unknown/custom steps without hallucinated production workflow code. | Unknown steps become explicit manual-review placeholders and low-confidence mappings. | CFM-008 |

## GitHub Actions Generation

| ID | Priority | Estimate | Story | Acceptance Criteria | Dependencies |
|---|---|---:|---|---|---|
| CFM-014 | P0 | 5 | Build migration planner that aggregates mappings, warnings, secrets, and confidence. | Planner emits one deterministic `MigrationPlan` with target workflow path and job plan. | CFM-009, CFM-010, CFM-011, CFM-012, CFM-013 |
| CFM-015 | P0 | 5 | Generate GitHub Actions workflow YAML. | Generator emits `name`, `on`, `jobs`, `runs-on`, steps, container, services, and environment as valid YAML. | CFM-014 |
| CFM-016 | P0 | 3 | Validate generated workflow shape before writing. | Validator rejects malformed YAML and missing `name`, `on`, or `jobs`. | CFM-015 |
| CFM-017 | P1 | 5 | Add branch/trigger strategy configuration. | User can choose default triggers or supply workspace setting defaults without code changes. | CFM-015 |
| CFM-018 | P2 | 5 | Improve GitHub Actions fidelity for Codefresh `when` conditions and parallel execution. | Common conditions and parallel step groups map to equivalent Actions expressions/jobs or produce clear warnings. | CFM-014 |

## VS Code Extension UX

| ID | Priority | Estimate | Story | Acceptance Criteria | Dependencies |
|---|---|---:|---|---|---|
| CFM-019 | P0 | 3 | Implement `scanWorkspace` command. | Command scans open workspace, shows result count, and logs files to output channel. | CFM-006 |
| CFM-020 | P0 | 5 | Implement `planMigration` command. | User can pick a pipeline and view a Markdown migration plan preview. | CFM-014, CFM-019 |
| CFM-021 | P0 | 5 | Implement `generateWorkflow` command with preview and confirmation. | Extension previews YAML, validates it, writes only after confirmation, and asks before overwrite. | CFM-015, CFM-016, CFM-020 |
| CFM-022 | P1 | 5 | Implement `explainMigration` command. | Command opens a concise migration explanation using Copilot when available and deterministic fallback otherwise. | CFM-020, CFM-027 |
| CFM-023 | P1 | 5 | Improve migration plan preview UX. | Preview includes grouped warnings, required secrets, confidence, and step mapping table. | CFM-020 |
| CFM-024 | P2 | 6 | Add tree view for pipeline inventory and migration status. | Activity view lists discovered pipelines, planned/generated state, warnings, and target workflow path. | CFM-019, CFM-020, CFM-021 |

## Copilot and AI Tooling

| ID | Priority | Estimate | Story | Acceptance Criteria | Dependencies |
|---|---|---:|---|---|---|
| CFM-025 | P0 | 5 | Register `@cfmigrator` chat participant with slash commands. | `/scan`, `/plan`, `/generate`, and `/explain` return useful results in VS Code Chat. | CFM-019, CFM-020, CFM-021 |
| CFM-026 | P0 | 5 | Register language model tools for scan, plan, and validate. | Copilot agent mode can invoke `scan_codefresh_pipelines`, `plan_codefresh_migration`, and `validate_github_workflow`. | CFM-006, CFM-014, CFM-016 |
| CFM-027 | P1 | 5 | Add Copilot-backed explanation flow with graceful fallback. | Uses Copilot model when available; handles missing model, consent denial, quota, and empty responses. | CFM-014 |
| CFM-028 | P1 | 5 | Add strict JSON AI review contract for unknown-step suggestions. | AI suggestions validate against schema and are discarded if malformed or unsafe. | CFM-013, CFM-027 |
| CFM-029 | P2 | 4 | Add prompt templates for ambiguity resolution. | Chat participant can ask focused follow-up questions for unsupported deploy/composition/custom patterns. | CFM-025, CFM-028 |

## Knowledge and Learning

| ID | Priority | Estimate | Story | Acceptance Criteria | Dependencies |
|---|---|---:|---|---|---|
| CFM-030 | P1 | 3 | Ship default mapping pattern library. | Repo includes `default-patterns.json` with clone, Docker, and approval patterns. | CFM-003 |
| CFM-031 | P1 | 5 | Initialize user override storage in VS Code global storage. | Extension creates a user pattern file if absent and never overwrites existing user patterns. | CFM-030 |
| CFM-032 | P2 | 5 | Add "learn this mapping" workflow. | User can save reviewed manual mappings into global storage and future plans consult those patterns. | CFM-028, CFM-031 |

## Testing and Quality

| ID | Priority | Estimate | Story | Acceptance Criteria | Dependencies |
|---|---|---:|---|---|---|
| CFM-033 | P0 | 5 | Add unit fixtures for required Codefresh scenarios. | Fixtures cover freestyle Node, Docker build/push, composition, approval, deploy, and unknown/custom steps. | CFM-007 |
| CFM-034 | P0 | 5 | Add mapper/generator unit tests. | Tests verify generated YAML and warnings for all required fixtures. | CFM-009, CFM-010, CFM-011, CFM-012, CFM-013, CFM-015 |
| CFM-035 | P0 | 3 | Add validator tests. | Tests prove valid workflows pass and missing required top-level fields fail. | CFM-016 |
| CFM-036 | P1 | 3 | Add mocked Copilot tests. | AI flows are tested with mocked model responses and no real Copilot calls. | CFM-027, CFM-028 |
| CFM-037 | P1 | 4 | Add VS Code extension-host integration smoke test. | Extension activates and registers expected commands in `@vscode/test-electron`. | CFM-002, CFM-019 |
| CFM-038 | P2 | 3 | Add CI workflow for compile and tests. | Pull requests run install, compile, unit tests, and optional integration smoke test. | CFM-034, CFM-037 |

## Packaging and Documentation

| ID | Priority | Estimate | Story | Acceptance Criteria | Dependencies |
|---|---|---:|---|---|---|
| CFM-039 | P1 | 3 | Document supported Codefresh mappings and known limitations. | Docs list supported step types, fallback behavior, required secrets, and manual review cases. | CFM-014 |
| CFM-040 | P1 | 3 | Add manual QA checklist for extension usage. | Checklist covers scan, plan, generate, overwrite protection, chat participant, and tools. | CFM-021, CFM-025, CFM-026 |
| CFM-041 | P2 | 3 | Add packaging script and VSIX verification. | `vsce package` or equivalent process is documented and package excludes dev artifacts. | CFM-001, CFM-004 |
| CFM-042 | P2 | 4 | Add sample migration walkthrough. | A sample Codefresh YAML and generated GitHub workflow are documented end to end. | CFM-039 |
