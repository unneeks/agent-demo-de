# Codefresh to GitHub Actions Migrator

Local-first VS Code extension that scans Codefresh pipeline YAML files and generates GitHub Actions workflow drafts. The converter uses deterministic parsing and mapping first, with GitHub Copilot used for explanations and review help.

## Commands

- `Codefresh Migrator: Scan Workspace`
- `Codefresh Migrator: Plan Migration`
- `Codefresh Migrator: Generate Workflow`
- `Codefresh Migrator: Explain Migration`

## Chat

Use `@cfmigrator` in VS Code Chat:

- `/scan`
- `/plan`
- `/generate`
- `/explain`

## Development

```sh
npm install
npm test
```
