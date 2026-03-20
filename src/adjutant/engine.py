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


class SCVOverseer:
    MODELS = ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-flash-lite"]

    def __init__(self, interval: int = 10):
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.project_root = os.path.dirname(self.base_dir)
        self.telemetry_dir = os.path.join(self.project_root, ".beads", "telemetry")
        self.registry_path = os.path.join(self.telemetry_dir, "active_scvs.json")

    def _is_process_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except Exception:
            # If we lack permission or hit other errors, assume it might be running
            return True

    def _check_scvs(self):
        if not os.path.exists(self.registry_path):
            return

        try:
            with open(self.registry_path, "r") as f:
                registry = json.load(f)
        except (json.JSONDecodeError, IOError):
            return

        updated_registry = False
        active_registry = {}

        for objective_id, scv_info in registry.items():
            pid = scv_info.get("pid")
            agent_name = scv_info.get("agent_name")
            
            if pid and not self._is_process_running(pid):
                log_path = os.path.join(self.telemetry_dir, f"{objective_id}.log")
                should_cleanup = True

                if os.path.exists(log_path):
                    try:
                        with open(log_path, "r") as f:
                            log_content = f.read()
                        
                        current_model = scv_info.get("model", self.MODELS[0])
                        # Detect capacity or quota errors
                        if any(s in log_content for s in ["MODEL_CAPACITY_EXHAUSTED", "RESOURCE_EXHAUSTED", "429", "QUOTA_EXHAUSTED", "TerminalQuotaError"]):
                            print(f"\n[Overseer] Detected capacity crash for SCV {objective_id} ({current_model}). Restarting with fallback model.")
                            
                            next_model = None
                            try:
                                current_idx = self.MODELS.index(current_model)
                                if current_idx + 1 < len(self.MODELS):
                                    next_model = self.MODELS[current_idx + 1]
                            except ValueError:
                                next_model = self.MODELS[1] # fallback to flash
                            
                            if next_model:
                                spawn_agent(agent_name, objective_id, starting_model=next_model)
                                updated_registry = True
                                # spawn_agent updates the registry file directly
                                continue
                            else:
                                print(f"[Overseer] All fallback models exhausted for {objective_id}.")
                    except IOError:
                        pass
                
                if should_cleanup:
                    cleanup_scv(objective_id, self.project_root)
                    updated_registry = True
            else:
                active_registry[objective_id] = scv_info
                
        if updated_registry:
            try:
                # Reload registry to ensure we don't overwrite new spawns
                if os.path.exists(self.registry_path):
                    with open(self.registry_path, "r") as f:
                        latest_registry = json.load(f)
                    latest_registry.update(active_registry)
                    # Remove only the ones we intended to remove
                    for obj_id in [k for k in latest_registry if k not in active_registry and k in registry]:
                         del latest_registry[obj_id]
                else:
                    latest_registry = active_registry

                with open(self.registry_path, "w") as f:
                    json.dump(latest_registry, f, indent=2)
            except IOError:
                pass

    def _run(self):
        while not self.stop_event.is_set():
            self._check_scvs()
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


def cleanup_scv(objective_id: str, project_root: str):
    """
    Cleans up the git worktree and pushes the branch to origin.
    """
    worktrees_dir = os.path.join(project_root, ".adjutant", "worktrees")
    worktree_path = os.path.join(worktrees_dir, objective_id)
    branch_name = f"scv/{objective_id}"
    resolved_system_prompt_path = os.path.join(worktrees_dir, f".resolved_system_{objective_id}.md")

    print(f"\n[Cleaning up SCV for {objective_id}]")

    # 1. Push the branch
    try:
        subprocess.run(
            ["git", "push", "origin", branch_name],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True
        )
        print(f"Pushed branch {branch_name} to origin.")
    except Exception as e:
        print(f"Failed to push branch {branch_name}: {e}")

    # 2. Cleanup worktree
    if os.path.exists(worktree_path):
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", worktree_path],
                cwd=project_root,
                check=False,
                capture_output=True,
                text=True
            )
            print(f"Removed worktree at {worktree_path}")
        except Exception as e:
            print(f"Failed to remove worktree {worktree_path}: {e}")

    # 3. Cleanup resolved system prompt
    if os.path.exists(resolved_system_prompt_path):
        try:
            os.remove(resolved_system_prompt_path)
            print(f"Removed resolved system prompt: {resolved_system_prompt_path}")
        except Exception as e:
            print(f"Failed to remove resolved system prompt: {e}")


def run_adjutant_agent(initial_directive: str):
    """
    Launches the Adjutant (Planner) agent as an interactive Gemini session.
    """
    print("\n[Adjutant Online: Initiating Mission Planning]")
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    adjutant_agent_dir = os.path.join(base_dir, "adjutant", "agents", "adjutant")
    system_prompt_path = os.path.join(adjutant_agent_dir, "system.md")
    
    with open(system_prompt_path, "r") as f:
        system_prompt = f.read()

    temp_prompt_path = os.path.join(base_dir, ".adjutant_resolved_system.md")
    with open(temp_prompt_path, "w") as f:
        f.write(system_prompt)
    
    env = os.environ.copy()
    env["GEMINI_SYSTEM_MD"] = temp_prompt_path
    
    policy_dir = os.path.join(adjutant_agent_dir, "policies")
    cmd = ["gemini", "--model", "gemini-3.1-pro-preview", "--policy", policy_dir, "-i", initial_directive]
    
    hud = AdjutantHUD(mission=initial_directive)
    hud.start()

    overseer = SCVOverseer()
    overseer.start()
    
    try:
        subprocess.run(cmd, env=env, check=False)
    except FileNotFoundError:
        print("Error: 'gemini' CLI not found. Please ensure it is installed and in your PATH.")
        sys.exit(1)
    except Exception as e:
        print(f"Error launching Adjutant: {e}")
        sys.exit(1)
    finally:
        hud.stop()
        overseer.stop()
        if os.path.exists(temp_prompt_path):
            os.remove(temp_prompt_path)


def spawn_agent(agent_name: str, objective_id: str, starting_model: str = None):
    """
    Spawns a sub-agent asynchronously.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agent_dir = os.path.join(base_dir, "adjutant", "agents", agent_name)
    system_prompt_path = os.path.join(agent_dir, "system.md")
    
    if not os.path.exists(system_prompt_path):
        raise ValueError(f"Unknown agent or missing system prompt: {agent_name}")

    with open(system_prompt_path, "r") as f:
        prompt_template = f.read()
    
    prompt = prompt_template.format(objective_id=objective_id)
    project_root = os.path.dirname(base_dir)

    worktrees_dir = os.path.join(project_root, ".adjutant", "worktrees")
    os.makedirs(worktrees_dir, exist_ok=True)
    worktree_path = os.path.join(worktrees_dir, objective_id)
    branch_name = f"scv/{objective_id}"

    env = os.environ.copy()
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
        if "already exists" in e.stderr or "already exists" in e.stdout:
            print(f"Worktree or branch already exists for {objective_id}. Proceeding.")
        else:
            raise RuntimeError(f"Failed to create git worktree: {e.stderr}")

    telemetry_dir = os.path.join(project_root, ".beads", "telemetry")
    os.makedirs(telemetry_dir, exist_ok=True)
    log_path = os.path.join(telemetry_dir, f"{objective_id}.log")
    
    # Resolve Git metadata for sandboxing
    try:
        git_common_dir = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], cwd=project_root, text=True).strip()
        git_dir = subprocess.check_output(["git", "rev-parse", "--git-dir"], cwd=worktree_path, text=True).strip()
        git_common_dir = os.path.abspath(os.path.join(project_root, git_common_dir))
        git_dir = os.path.abspath(os.path.join(worktree_path, git_dir))
    except Exception:
        git_common_dir = os.path.join(project_root, ".git")
        git_dir = os.path.join(worktree_path, ".git")

    model = starting_model or "gemini-3.1-pro-preview"
    print(f"--- Spawning sub-agent with model: {model} ---")
    
    cmd = [
        "gemini", 
        "--model", model, 
        "--policy", policy_dir, 
        "--include-directories", project_root, 
        "--include-directories", os.path.join(project_root, ".beads"), 
        "--include-directories", git_common_dir,
        "--include-directories", git_dir,
        "--yolo", 
        "--sandbox", 
        "-p", "Execute mission."
    ]
    
    log_file = open(log_path, "a")
    process = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=log_file,
        cwd=worktree_path,
        env=env,
        start_new_session=True
    )
    log_file.close()

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
        "agent_name": agent_name,
        "model": model
    }
    
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)

    print(f"Spawned {agent_name} for {objective_id}. Logging to {log_path}")
