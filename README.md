# Adjutant: Interactive AI Strategic Planner

## Overview
**Adjutant** is an autonomous AI strategic planner and orchestrator. It uses the **Gemini CLI** and the **Beads (`bd`) CLI** to help you execute complex development "Missions" by decomposing them into a graph of "Objectives" and delegating work to specialized sub-agents.

Unlike typical daemon-based orchestrators, the Adjutant is an **interactive agent session**. When you launch a mission, you enter a conversation with the Adjutant, who uses its planning persona to help you build and manage the task graph.

## Getting Started

To launch a new mission, use the `adjutant` command followed by your mission directive:

```bash
adjutant "Implement a fullstack web calculator with React and FastAPI"
```

This will:
1.  **Initialize the Adjutant Persona**: Injects a specialized "Planner" system prompt into the Gemini CLI.
2.  **Start an Interactive Session**: You can refine the plan, approve `bd` task creation, and monitor progress.
3.  **Spawn SCV Sub-Agents**: The Adjutant can delegate technical work (coding, testing) to specialized worker sub-agents (`scv-coder`, `scv-tester`) as tools.

## Core Concepts

### Missions and Objectives
- **Mission**: A high-level goal, represented as an **Epic** bead in `bd`.
- **Objective**: A specific, actionable task, bug fix, or chore, represented as a **Bead** with dependencies and status.

### The Sub-Agent Workforce (SCVs)
The Adjutant can call upon specialized sub-agents:
- **`scv-coder`**: Handles implementation, refactoring, and bug fixes.
- **`scv-tester`**: Handles verification, running tests, and managing test failures (Red Alert Pivots).

## The Workflow

1.  **Mission Intake**: You provide a high-level goal.
2.  **Interactive Planning**: The Adjutant proposes a plan and uses `bd create` to build the task graph.
3.  **Delegation**: The Adjutant calls sub-agents (e.g., `scv_coder("Implement the login API for bd-123")`) as tools.
4.  **Completion**: Once all objectives are closed and the mission is successful, the Adjutant helps you "Land the Plane" by finalizing the changes and pushing to the remote.

## Development Setup

The Adjutant is implemented in Python and orchestrates work via the `gemini` and `bd` CLIs.

To run the local development version:
```bash
# From the project root
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
python -m adjutant.cli "My New Mission"
```

## Mandatory Workflow for Agents
All agents (Adjutant and SCVs) must follow the rules defined in [AGENTS.md](AGENTS.md), especially regarding the use of the `bd` CLI as the sole source of truth for task state.
