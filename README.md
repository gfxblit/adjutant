# Adjutant: Data-Flow Autonomous Development

## Overview
This document outlines the architecture for **Adjutant**, an autonomous AI development loop. It replaces complex state-machine orchestrators (like LangGraph) with a simple, data-driven orchestration model powered by the **Beads (`bd`) CLI** and the **Gemini CLI**.

The core philosophy is to shift from **Control Flow Orchestration** to **Data Flow Orchestration** where agents independently pull work from a persistent, git-backed task graph.

*Theming:* We use a Terran (StarCraft) inspired vocabulary. The user interacts with the **Adjutant** (the entry point/Planner), which manages **Missions** (Epics) broken down into **Objectives** (Beads). The work is executed by **SCVs** (Worker Agents powered by `gemini-cli`).

## Core Principles
1. **Beads as the Sole Source of Truth:** All goals, tasks, bugs, and agent assignments are represented as Beads (Objectives) in the `.beads` directory. 
2. **Declarative Dependency Graph:** Work ordering is determined natively by Beads dependencies (`bd dep add <blocked> <blocker>`). An SCV can only see an Objective when all its blockers are resolved.
3. **Role-Based Routing:** The daemon loop simply spawns SCVs to work on specific Objectives labeled with their role (e.g., `role:scv-coder`, `role:scv-tester`).
4. **Agent Autonomy:** The SCVs (running via `gemini-cli`) use their own native shell capabilities to interact with the `bd` CLI directly, based on their system prompts. The engine does not need to wrap these commands for them.

## The Architecture

### 1. The Global Mission & The Adjutant (Planning Phase)
Every high-level user request starts by invoking the **Adjutant**:
`adjutant "Implement a new calculator module"`

The Adjutant serves as the Planner:
- It creates a **Mission** (`bd create -t epic ...`).
- It breaks the Mission down into specific implementation Objectives (`bd create -t task ...`).
- It creates verification Objectives (`bd create -t chore ...`).
- It wires up the dependency graph, blocking verification with implementation (`bd dep add ...`).
- It assigns roles via labels (`bd label add ... role:scv-coder`).

*Note: The Adjutant itself could be powered by a `gemini-cli` instance with a specific "Planner" prompt that instructs it to use the `bd` CLI to build out the graph.*

### 2. The Execution Engine (The Base Loop)
Once the Adjutant has planned the Mission, a lightweight `while` loop polls the database for "ready" work and drops an SCV to execute it.

```python
import subprocess
import json
import time

def get_ready_objectives(role: str) -> list[str]:
    # The engine only needs enough `bd` awareness to drive the loop.
    cmd = ["bd", "list", "--ready", f"--label=role:{role}", "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        try:
            beads = json.loads(result.stdout)
            return [b['id'] for b in beads]
        except json.JSONDecodeError:
            pass
    return []

def run_base_loop(mission_id: str):
    print(f"Adjutant online. Monitoring Mission {mission_id}...")
    
    while not is_mission_closed(mission_id):
        # 1. Check for Coding Objectives
        coder_objectives = get_ready_objectives("scv-coder")
        if coder_objectives:
            print(f"Deploying SCV-Coder to Objective {coder_objectives[0]}")
            run_scv(coder_objectives[0], "coder")
            continue # Restart loop to re-evaluate the graph

        # 2. Check for Testing/Verification Objectives
        tester_objectives = get_ready_objectives("scv-tester")
        if tester_objectives:
            print(f"Deploying SCV-Tester to Objective {tester_objectives[0]}")
            run_scv(tester_objectives[0], "tester")
            continue # Restart loop

        print("Awaiting further directives or human intervention...")
        time.sleep(5)
```

### 3. The SCVs (Powered by Gemini CLI)
The SCVs are driven by `gemini-cli` instances. The engine does not micromanage them; it simply drops them into the environment with a strict system prompt and an Objective ID.

When `run_scv(objective_id, role)` is called, the loop spawns a subprocess:

**Example SCV-Coder Execution:**
```bash
gemini-cli --system-prompt "You are an SCV-Coder. Your current Objective is $OBJECTIVE_ID. 
1. Run 'bd show $OBJECTIVE_ID' to read your parameters. 
2. Write the necessary code to fulfill the parameters. 
3. Once complete, run 'bd close $OBJECTIVE_ID' to signal job completion." \
"Execute Objective $OBJECTIVE_ID"
```

**Example SCV-Tester Execution:**
```bash
gemini-cli --system-prompt "You are an SCV-Tester. Your current Objective is $OBJECTIVE_ID. 
1. Run tests to verify the recent code changes. 
2. If tests pass, run 'bd close $OBJECTIVE_ID'. 
3. If tests fail, you must create a block: run 'bd create -t bug ...' containing the stack trace, label it 'role:scv-coder', and block your current Objective by running 'bd dep add $OBJECTIVE_ID <new-bug-id>'." \
"Verify Objective $OBJECTIVE_ID"
```

### 4. Handling Failures (The Red Alert Pivot)
When a test fails, the SCV-Tester alters the graph natively via its shell tools.
- **Trigger:** SCV-Tester (Gemini CLI) runs `pytest` and it fails.
- **Action:** The SCV-Tester follows its prompt instructions, natively running `bd create`, `bd label add`, and `bd dep add`.
- **Result:** The `gemini-cli` process ends. On the next iteration of the Adjutant `while` loop, the tester Objective is blocked, and the new bug Objective surfaces for the SCV-Coder.

## Implementation Roadmap
1. **Engine Shell:** Write the core `adjutant` Python script with the `while` loop and `subprocess` calls to `gemini-cli`.
2. **Prompt Migration:** Extract the Coder and Tester system prompts from the legacy `copium-loop` repository, adapting them to include instructions on how to use the `bd` CLI natively.
3. **The Planner Prompt:** Create a system prompt for the initial Adjutant execution so it knows how to break down a "Mission" into `bd` tasks and chores with dependencies.