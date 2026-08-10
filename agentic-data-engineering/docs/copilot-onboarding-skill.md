# Interactive Copilot Onboarding Wizard

## Overview

The interactive onboarding wizard allows you to onboard new projects into the Agentic Data Engineering Evolution Platform's dual-twin graph effortlessly by chatting with GitHub Copilot (or an equivalent AI Agent). 

Instead of writing custom Python CLI wizard code (`scripts/onboard_project.py` interactivity), we dogfood the agentic approach: an AI agent conducts the interview, gathers your parameters, and then seamlessly drives the underlying Python CLI for you.

## The One Idea That Must Not Be Compromised

**The agent is an interface layer over the pure engine CLI.**
The Copilot agent does not attempt to reinvent or write custom Python code for ingestion. Its sole purpose is to act as an interactive conversational interface that builds the exact `scripts/onboard_project.py` CLI invocation required. 

## Using the Wizard

1. Open your Copilot chat interface (e.g., inside VS Code, GitHub Workspace, or similar supported IDEs).
2. Invoke the onboarding prompt by referencing the file or typing the trigger (e.g., `@workspace /onboard-project`).
3. The agent will greet you and begin the interview process, asking for:
   - Backend choice (`memory` or `postgres-neo4j`)
   - Project ID and Name
   - Target Repository Root
   - Optional metadata (Technologies, Owners, Domain, Criticality)
4. Respond naturally to the prompts.
5. Once all information is collected, the agent will present the final command and execute it (or provide it for you to execute).
6. It will then optionally help you launch the Web UI to view your new project graph.

## File Locations
- **Prompt Definition**: `agentic-data-engineering/.github/prompts/onboard-project.prompt.md`
- **Underlying Script**: `scripts/onboard_project.py`
- **ADR**: [ADR-0023: Copilot Onboarding Skill](adr/0023-copilot-onboarding-skill.md)
