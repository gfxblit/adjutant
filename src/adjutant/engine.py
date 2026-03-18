import os
import subprocess
import sys
import threading
import json

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
    adjutant_agent_dir = os.path.join(base_dir, "adjutant", "agents", "adjutant")
    system_prompt_path = os.path.join(adjutant_agent_dir, "system.md")
    
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
    
    # Policy directory for the main Adjutant agent
    policy_dir = os.path.join(adjutant_agent_dir, "policies")
    
    # Launch gemini in interactive mode (-i) with the initial directive, policy, and model
    cmd = ["gemini", "--model", "gemini-3.1-pro-preview", "--policy", policy_dir, "-i", initial_directive]
    
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
    # Resolve paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agent_dir = os.path.join(base_dir, "adjutant", "agents", agent_name)
    system_prompt_path = os.path.join(agent_dir, "system.md")
    
    if not os.path.exists(system_prompt_path):
        raise ValueError(f"Unknown agent or missing system prompt: {agent_name}")

    # Read the agent's system prompt and create a resolved temporary version
    with open(system_prompt_path, "r") as f:
        prompt_template = f.read()
    
    prompt = prompt_template.format(objective_id=objective_id)
    
    project_root = os.path.dirname(base_dir)

    # Create isolated git worktree for the SCV
    worktrees_dir = os.path.join(project_root, ".adjutant", "worktrees")
    os.makedirs(worktrees_dir, exist_ok=True)
    worktree_path = os.path.join(worktrees_dir, objective_id)
    branch_name = f"scv/{objective_id}"

    # Prepare environment for the sub-agent
    env = os.environ.copy()
    
    # We resolve the system prompt and save it in the worktree so the sub-agent uses it
    resolved_system_prompt_path = os.path.join(worktrees_dir, f".resolved_system_{objective_id}.md")
    with open(resolved_system_prompt_path, "w") as f:
        f.write(prompt)
    
    env["GEMINI_SYSTEM_MD"] = resolved_system_prompt_path

    policy_dir = os.path.join(agent_dir, "policies")

    try:
        subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, worktree_path],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True
        )
        print(f"Created worktree at {worktree_path} on branch {branch_name}")
    except subprocess.CalledProcessError as e:
        # If branch or worktree already exists, it might be a retry.
        if "already exists" in e.stderr or "already exists" in e.stdout:
            print(f"Worktree or branch already exists for {objective_id}. Proceeding.")
        else:
            raise RuntimeError(f"Failed to create git worktree: {e.stderr}")

    telemetry_dir = os.path.join(project_root, ".beads", "telemetry")
    os.makedirs(telemetry_dir, exist_ok=True)
    
    log_path = os.path.join(telemetry_dir, f"{objective_id}.log")
    
    # Launch gemini headless asynchronously, with a fallback chain for quota limits
    bash_script = (
        'for model in "gemini-3.1-pro-preview" "gemini-3-flash-preview" "gemini-2.5-flash-lite"; do '
        'echo "--- Spawning sub-agent with model: $model ---"; '
        f'gemini --model "$model" --policy "{policy_dir}" --include-directories . --include-directories .beads --yolo --sandbox -p "$1" && exit 0; '
        'echo "\\n[!] Model $model failed. Trying next fallback..."; '
        'done; '
        'echo "\\n[!] All fallback models exhausted."; exit 1'
    )
    cmd = ["bash", "-c", bash_script, "_", "Execute mission."]
    
    # We use a context manager to open the file, but Popen will inherit the FD.
    log_file = open(log_path, "w")
    process = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=log_file,
        cwd=worktree_path,
        env=env,
        start_new_session=True
    )
    log_file.close()

    # Update active SCV registry
    registry_path = os.path.join(telemetry_dir, "active_scvs.json")
    try:
        if os.path.exists(registry_path):
            with open(registry_path, "r") as f:
                registry = json.load(f)
        else:
            registry = {}
    except (json.JSONDecodeError, IOError):
        registry = {}
    
    registry[objective_id] = {
        "pid": process.pid,
        "agent_name": agent_name
    }
    
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)

    print(f"Spawned {agent_name} for {objective_id}. Logging to {log_path}")
