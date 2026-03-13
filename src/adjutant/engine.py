import subprocess
import json
import time

from adjutant.prompts import SCV_CODER_PROMPT, SCV_TESTER_PROMPT

def get_ready_objectives(role: str) -> list[str]:
    # Poll bd for ready objectives assigned to a specific role
    cmd = ["bd", "list", "--ready", f"--label=role:{role}", "--json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            beads = json.loads(result.stdout)
            return [b['id'] for b in beads]
    except Exception as e:
        print(f"Error querying bd: {e}")
    return []

def run_scv(objective_id: str, role: str):
    print(f"\n[Deploying SCV-{role.upper()} to Objective {objective_id}]")
    if role == "coder":
        system_prompt = SCV_CODER_PROMPT.format(objective_id=objective_id)
    elif role == "tester":
        system_prompt = SCV_TESTER_PROMPT.format(objective_id=objective_id)
    else:
        print(f"Unknown role: {role}")
        return

    cmd = [
        "gemini-cli",
        "--system-prompt", system_prompt,
        f"Execute Objective {objective_id}"
    ]
    
    try:
        # Execute the SCV, streaming output to the terminal
        subprocess.run(cmd, check=False)
    except Exception as e:
        print(f"Error executing SCV: {e}")

def run_base_loop(mission_id: str = None):
    print("Adjutant online. Monitoring Objectives...")
    if mission_id:
        print(f"Restricting context to Mission: {mission_id}")
    
    # Ideally, we would check if mission is closed here, but for now we poll indefinitely
    # until interrupted.
    try:
        while True:
            # 1. Check for Coding Objectives
            coder_objectives = get_ready_objectives("scv-coder")
            if coder_objectives:
                run_scv(coder_objectives[0], "coder")
                continue # Restart loop to re-evaluate the graph

            # 2. Check for Testing/Verification Objectives
            tester_objectives = get_ready_objectives("scv-tester")
            if tester_objectives:
                run_scv(tester_objectives[0], "tester")
                continue # Restart loop

            print("Awaiting further directives or human intervention...", end="\r")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nAdjutant offline.")
