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
3.  **Delegate to SCV Sub-Agents**: The Adjutant delegates technical work (coding, testing) by spawning specialized worker sub-agents (`scv-coder`, `scv-tester`) asynchronously using the `adjutant run-agent` command.

## CLI Subcommands

### `adjutant plan [mission]`
Starts an interactive mission planning session. This is the default behavior if no subcommand is provided.

### `adjutant run-agent <agent> <objective_id>`
Manually spawns a specialized sub-agent to work on a specific objective.

- **`agent`**: One of `scv-coder` or `scv-tester`.
- **`objective_id`**: The ID of the `bd` objective (e.g., `adjutant-aq1`).

## Core Concepts

### Missions and Objectives
- **Mission**: A high-level goal, represented as an **Epic** bead in `bd`.
- **Objective**: A specific, actionable task, bug fix, or chore, represented as a **Bead** with dependencies and status.

### The Sub-Agent Workforce (SCVs)
The Adjutant can call upon specialized sub-agents:
- **`scv-coder`**: Handles implementation, refactoring, and bug fixes.
- **`scv-tester`**: Handles verification, running tests, and managing test failures (Red Alert Pivots).

Sub-agents are spawned **asynchronously** in the background. Their execution is headless, and all output is captured in telemetry logs located at `.beads/telemetry/<objective_id>.log`.

## The Workflow

1.  **Mission Intake**: You provide a high-level goal.
2.  **Interactive Planning**: The Adjutant proposes a plan and uses `bd create` to build the task graph.
3.  **Delegation**: The Adjutant spawns sub-agents asynchronously to work on specific objectives.
4.  **Monitoring**: You can monitor progress via the terminal HUD or by tailing the telemetry logs.
5.  **Completion**: Once all objectives are closed and the mission is successful, the Adjutant helps you "Land the Plane" by finalizing the changes and pushing to the remote.

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
