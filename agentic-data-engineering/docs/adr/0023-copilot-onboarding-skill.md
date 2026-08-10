# 0023: Copilot Onboarding Skill

**Status:** Accepted

## Context

Phase 1-9 built the backend graph and engines. We recently introduced `scripts/onboard_project.py` (ADR-0022), which provides a guided, interactive entry point to onboarding by calling `ProjectGraphService.register_project()`, `discover_project()`, and `run_cycle()`. 

While `onboard_project.py` is interactive, we want to push the "Agentic" philosophy further by orchestrating the entire onboarding workflow via AI agents (specifically GitHub Copilot) rather than writing custom interactive Python UI code. 

## Decision

We will implement the interactive onboarding wizard purely as a **GitHub Copilot Prompt/Skill** instead of writing new Python-based interactive prompts. 

We are adding `.github/prompts/onboard-project.prompt.md` to instruct Copilot on how to interview the user, collect the required onboarding parameters, and then execute the underlying `scripts/onboard_project.py` non-interactively using CLI flags.

## Consequences

* **Zero new Python code**: The interaction logic relies entirely on Copilot's contextual understanding and conversational capabilities.
* **Agentic orchestration**: We dogfood the agentic architecture by having an agent drive the onboarding process.
* **Decoupling**: The underlying `scripts/onboard_project.py` remains a pure CLI wrapper around the Python APIs, keeping business logic distinct from the user interface.

## Alternatives rejected

* **Building a rich CLI UI (e.g., using `Rich` or `Inquirer`)**: Rejected. This goes against the agentic philosophy and adds unnecessary UI-layer code to maintain.
* **Building a web-based onboarding wizard in `webui/`**: Deferred/Rejected. While a GUI might be built eventually, leveraging Copilot as the interactive interface provides immediate value with zero code footprint.
