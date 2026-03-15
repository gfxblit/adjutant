import os
import subprocess
import sys
import threading
import json
from .prompts import SCV_CODER_PROMPT, SCV_TESTER_PROMPT

class AdjutantHUD:
    def __init__(self, mission: str, interval: int = 5):
        self.mission = mission
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None

    def update_hud(self):
        try:
            # Run bd status --json
            output = subprocess.check_output(["bd", "status", "--json"], stderr=subprocess.DEVNULL)
            status_data = json.loads(output)
            summary = status_data.get("summary", {})
            
            total = summary.get("total_issues", 0)
            open_issues = summary.get("open_issues", 0)
            closed_issues = summary.get("closed_issues", 0)
            
            progress = (closed_issues / total * 100) if total > 0 else 0
            
            # Format title string
            # Title: Mission: {MISSION} | {PROGRESS}% | Open: {OPEN}, Closed: {CLOSED}
            title = f"Mission: {self.mission} | {progress:.1f}% | Open: {open_issues}, Closed: {closed_issues}"
            
            # Update terminal title using ANSI escape sequence
            sys.stdout.write(f"\033]0;{title}\007")
            sys.stdout.flush()
        except Exception:
            # Silently fail if something goes wrong during HUD update
            pass

    def _run(self):
        while not self.stop_event.is_set():
            self.update_hud()
            # Wait for interval or until stop_event is set
            self.stop_event.wait(self.interval)

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def stop(self):
        if self.thread:
            self.stop_event.set()
            self.thread.join(timeout=1.0)

def run_adjutant_agent(initial_directive: str):
    """
    Launches the Adjutant (Planner) agent as an interactive Gemini session.
    The Adjutant's specialized persona is injected via GEMINI_SYSTEM_MD.
    """
    print("\n[Adjutant Online: Initiating Mission Planning]")
    
    # Resolve the path to the Adjutant's system prompt
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    system_prompt_path = os.path.join(base_dir, "adjutant", "adjutant_system.md")
    
    # Read the base system prompt
    with open(system_prompt_path, "r") as f:
        system_prompt = f.read()

    # Write the resolved prompt to a temporary file for the session
    temp_prompt_path = os.path.join(base_dir, ".adjutant_resolved_system.md")
    with open(temp_prompt_path, "w") as f:
        f.write(system_prompt)
    
    # Configure the environment to override the system prompt
    env = os.environ.copy()
    env["GEMINI_SYSTEM_MD"] = temp_prompt_path
    
    # Launch gemini in interactive mode (-i) with the initial directive
    cmd = ["gemini", "-i", initial_directive]
    
    # Initialize and start the Parallel HUD
    hud = AdjutantHUD(mission=initial_directive)
    hud.start()
    
    try:
        subprocess.run(cmd, env=env, check=False)
    except FileNotFoundError:
        print("Error: 'gemini' CLI not found. Please ensure it is installed and in your PATH.")
        sys.exit(1)
    except Exception as e:
        print(f"Error launching Adjutant: {e}")
        sys.exit(1)
    finally:
        # Stop the HUD thread
        hud.stop()
        # Clean up the temporary prompt
        if os.path.exists(temp_prompt_path):
            os.remove(temp_prompt_path)

def spawn_agent(agent_name: str, objective_id: str):
    """
    Spawns a sub-agent asynchronously.
    """
    prompts = {
        "scv-coder": SCV_CODER_PROMPT,
        "scv-tester": SCV_TESTER_PROMPT,
    }
    
    if agent_name not in prompts:
        raise ValueError(f"Unknown agent name: {agent_name}")
    
    prompt_template = prompts[agent_name]
    prompt = prompt_template.format(objective_id=objective_id)
    
    # Resolve project root to find .beads directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(base_dir)
    telemetry_dir = os.path.join(project_root, ".beads", "telemetry")
    os.makedirs(telemetry_dir, exist_ok=True)
    
    log_path = os.path.join(telemetry_dir, f"{objective_id}.log")
    
    # Launch gemini headless asynchronously
    cmd = ["gemini", "-p", prompt]
    
    # We use a context manager to open the file, but Popen will inherit the FD.
    # On Unix-like systems, the child process keeps the file descriptor open 
    # even after the parent closes its file object, as long as it's not O_CLOEXEC.
    log_file = open(log_path, "w")
    subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True
    )
    # We should not close log_file here immediately if we want to be safe, 
    # but Popen should have duplicated it. 
    # However, to be absolutely sure and avoid leaks in the parent, we can close it.
    log_file.close()

    print(f"Spawned {agent_name} for {objective_id}. Logging to {log_path}")
