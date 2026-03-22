import os
import subprocess
import sys
import threading
import json
import logging
from typing import Optional

# Setup logger
logger = logging.getLogger("adjutant")

def setup_logging(to_stdout: bool = False, log_file: Optional[str] = None):
    """
    Configures the adjutant logger.
    """
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    logger.setLevel(logging.INFO)
    
    # We use a formatter for file logging, but for stdout we might want a simpler one
    # or none at all if we are mimicking print.
    # To mimic print, we use a simple formatter or just the message.
    if to_stdout:
        handler = logging.StreamHandler(sys.stdout)
        # No special format for stdout to keep it clean and mimic print
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    
    if log_file:
        # Ensure directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)
        logger.addHandler(handler)


def is_process_running(pid: int) -> bool:
    """Checks if a process with a given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        # If we lack permission or hit other errors, assume it might be running
        return True


def get_project_root() -> str:
    """Gets the main project root, resolving from within worktrees if necessary."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.dirname(base_dir)
    # Check if we are in an SCV worktree
    if ".adjutant" in root and "worktrees" in root:
        # Move up from .adjutant/worktrees/objective_id
        root = os.path.dirname(os.path.dirname(os.path.dirname(root)))
    return root


def get_active_scvs(project_root: str) -> dict:
    """
    Scans worktrees for .scv_info.json files and returns a dictionary of active SCVs.
    Active means the process with the PID in .scv_info.json is still running.
    """
    worktrees_dir = os.path.join(project_root, ".adjutant", "worktrees")
    active_scvs = {}

    if not os.path.exists(worktrees_dir):
        return active_scvs

    for entry in os.listdir(worktrees_dir):
        worktree_path = os.path.join(worktrees_dir, entry)
        if os.path.isdir(worktree_path) and not entry.startswith('.'):
            scv_info_path = os.path.join(worktree_path, ".scv_info.json")
            if os.path.exists(scv_info_path):
                try:
                    with open(scv_info_path, "r") as f:
                        scv_info = json.load(f)

                    pid = scv_info.get("pid")
                    if pid and is_process_running(pid):
                        active_scvs[entry] = scv_info
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Could not read or parse SCV info from {scv_info_path}: {e}")
    return active_scvs


class AdjutantHUD:
    def __init__(self, mission: str, interval: int = 5):
        self.mission = mission
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None
        self.project_root = get_project_root()

    def update_hud(self):
        try:
            # Default values if bd fails
            progress = 0.0
            open_issues = 0
            closed_issues = 0
            in_progress = 0
            total = 0
            
            # 1. Get Mission status from bd
            try:
                # Run bd status --json with a timeout
                output = subprocess.check_output(["bd", "status", "--json"], stderr=subprocess.DEVNULL, timeout=2.0)
                status_data = json.loads(output)
                summary = status_data.get("summary", {})
                
                total = summary.get("total_issues", 0)
                open_issues = summary.get("open_issues", 0)
                closed_issues = summary.get("closed_issues", 0)
                in_progress = summary.get("in_progress_issues", 0)
                
                progress = (closed_issues / total * 100) if total > 0 else 0
            except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError, subprocess.TimeoutExpired):
                # If bd fails, we just use defaults for mission status
                pass
            
            # 2. Get SCV status by scanning worktrees
            registry = get_active_scvs(self.project_root)
            scv_count = len(registry)
            scv_list = sorted(list(registry.keys()))

            # Format title string
            # Title: Mission: {MISSION} | {PROGRESS}% | {CLOSED}/{TOTAL} | Open: {OPEN}, IP: {IN_PROGRESS}
            title = f"Mission: {self.mission} | {progress:.1f}% | {closed_issues}/{total} | Open: {open_issues}, IP: {in_progress}"
            
            if scv_count > 0:
                short_ids = [s.replace("adjutant-", "") for s in scv_list]
                # Limit length of listed SCVs in the title bar
                list_str = ", ".join(short_ids[:3])
                if scv_count > 3:
                    list_str += "..."
                title += f" | SCVs: {scv_count} ({list_str})"
            
            # Update terminal title using ANSI escape sequence
            sys.stdout.write(f"\033]0;{title}\007")
            sys.stdout.flush()
        except Exception:
            # Silently fail for unexpected errors during HUD update
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
        self.project_root = get_project_root()
        self.telemetry_dir = os.path.join(self.project_root, ".adjutant", "logs")

    def _get_registry_from_worktrees(self):
        """Scans .adjutant/worktrees for .scv_info.json files to build the registry."""
        worktrees_dir = os.path.join(self.project_root, ".adjutant", "worktrees")
        registry = {}
        if not os.path.exists(worktrees_dir):
            return registry
            
        try:
            for entry in os.listdir(worktrees_dir):
                if entry.startswith('.'):
                    continue
                worktree_path = os.path.join(worktrees_dir, entry)
                if os.path.isdir(worktree_path):
                    scv_info_path = os.path.join(worktree_path, ".scv_info.json")
                    if os.path.exists(scv_info_path):
                        try:
                            with open(scv_info_path, "r") as f:
                                scv_info = json.load(f)
                                registry[entry] = scv_info
                        except (json.JSONDecodeError, IOError):
                            pass
        except OSError:
            pass
        return registry

    def _check_scvs(self):
        '''
        Scans worktrees for SCVs, checks their running status, and cleans up if necessary.
        '''
        registry_from_worktrees = self._get_registry_from_worktrees()
        
        if not registry_from_worktrees:
            return # Nothing more to do if no SCVs found

        # Iterate through SCVs found in worktrees
        for objective_id, scv_info in registry_from_worktrees.items():
            pid = scv_info.get("pid")
            agent_name = scv_info.get("agent_name")
            current_model = scv_info.get("model", self.MODELS[0]) # Get model for potential restart
            
            # Check if the process is running. If not, clean it up.
            if pid and not is_process_running(pid):
                log_path = os.path.join(self.telemetry_dir, f"{objective_id}.log")
                logger.warning(f"[Overseer] SCV for {objective_id} (PID: {pid}, Model: {current_model}) not running. Checking for restart conditions.")
                
                should_restart = False
                # Check for specific crash conditions like capacity or quota errors
                if os.path.exists(log_path):
                    try:
                        with open(log_path, "r") as f:
                            log_content = f.read()
                        
                        if any(s in log_content for s in ["MODEL_CAPACITY_EXHAUSTED", "RESOURCE_EXHAUSTED", "429", "QUOTA_EXHAUSTED", "TerminalQuotaError"]):
                            logger.info(f"[Overseer] Detected crash for {objective_id} ({current_model}). Attempting restart with fallback model.")
                            should_restart = True
                            
                            next_model = None
                            try:
                                current_idx = self.MODELS.index(current_model)
                                if current_idx + 1 < len(self.MODELS):
                                    next_model = self.MODELS[current_idx + 1]
                            except ValueError:
                                next_model = self.MODELS[1] # fallback to flash
                            
                            if next_model:
                                logger.info(f"[Overseer] Restarting {objective_id} with model: {next_model}")
                                spawn_agent(agent_name, objective_id, starting_model=next_model)
                                continue 
                            else:
                                logger.warning(f"[Overseer] All fallback models exhausted for {objective_id}. Not restarting.")
                    except IOError:
                        logger.warning(f"[Overseer] Could not read log file {log_path} for {objective_id}.")
                
                # If not restarting, proceed with cleanup.
                if not should_restart:
                    logger.info(f"[Overseer] Cleaning up SCV for {objective_id} as it is not running and not eligible for restart.")
                    cleanup_scv(objective_id, self.project_root)

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


class SyncOverseer:
    def __init__(self, interval: int = 300): # 5 minutes
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None
        self.project_root = get_project_root()

    def _check_sync(self):
        try:
            # 1. Fetch origin main to get latest state
            subprocess.run(["git", "fetch", "origin", "main"], cwd=self.project_root, capture_output=True, check=False)
            
            # 2. Get list of open objectives from bd
            output = subprocess.check_output(["bd", "list", "--json"], cwd=self.project_root, text=True)
            objectives = json.loads(output)
            
            # 3. Get active SCVs to avoid spawning multiple agents for same objective
            active_scvs = get_active_scvs(self.project_root)
            active_objectives = list(active_scvs.keys())

            for obj in objectives:
                obj_id = obj["id"]
                if obj["status"] != "open" or obj_id in active_objectives:
                    continue
                
                branch_name = f"scv/{obj_id}"
                # Check if branch exists
                res = subprocess.run(["git", "show-ref", "--verify", f"refs/heads/{branch_name}"], cwd=self.project_root, capture_output=True)
                if res.returncode != 0:
                    continue
                
                # Check if behind origin/main
                res = subprocess.run(["git", "rev-list", "--count", f"{branch_name}..origin/main"], cwd=self.project_root, capture_output=True, text=True)
                if res.returncode == 0:
                    count = int(res.stdout.strip())
                    if count > 0:
                        logger.info(f"\n[SyncOverseer] Objective {obj_id} is behind origin/main by {count} commits. Triggering sync.")
                        directive = (
                            f"Sync branch '{branch_name}' with 'origin/main' using 'git pull --rebase origin main'. "
                            "MANDATORY: Resolve any conflicts and force-push the results. "
                            "If you cannot resolve conflicts automatically, report a 'Red Alert' in your telemetry and stop. "
                            "Otherwise, close this objective only if it was a dedicated sync task, "
                            "or just finish if you are an SCV-Coder resuming work."
                        )
                        spawn_agent("scv-coder", obj_id, directive=directive)

        except Exception:
            pass

    def _run(self):
        while not self.stop_event.is_set():
            self._check_sync()
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

    logger.info(f"\n[Cleaning up SCV for {objective_id}]")

    # 1. Auto-commit any pending changes in the worktree
    if os.path.exists(worktree_path):
        try:
            subprocess.run(
                ["git", "add", "."],
                cwd=worktree_path,
                check=False,
                capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", f"Auto-commit stranded work for {objective_id}"],
                cwd=worktree_path,
                check=False,
                capture_output=True
            )
            logger.info(f"Auto-committed any stranded changes in {worktree_path}.")
        except Exception as e:
            logger.info(f"Failed to auto-commit in worktree {worktree_path}: {e}")

    # 2. Push the branch
    try:
        subprocess.run(
            ["git", "push", "origin", branch_name],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True
        )
        logger.info(f"Pushed branch {branch_name} to origin.")
    except Exception as e:
        logger.info(f"Failed to push branch {branch_name}: {e}")

    # 3. Cleanup worktree
    if os.path.exists(worktree_path):
        try:
            subprocess.run(
                ["bd", "worktree", "remove", "--force", worktree_path],
                cwd=project_root,
                check=False,
                capture_output=True,
                text=True
            )
            logger.info(f"Removed worktree at {worktree_path} via 'bd worktree' (force=True)")
        except Exception as e:
            logger.info(f"Failed to remove worktree {worktree_path} via 'bd worktree': {e}")

    # 4. Cleanup resolved system prompt
    if os.path.exists(resolved_system_prompt_path):
        try:
            os.remove(resolved_system_prompt_path)
            logger.info(f"Removed resolved system prompt: {resolved_system_prompt_path}")
        except Exception as e:
            logger.info(f"Failed to remove resolved system prompt: {e}")


def recover_orphaned_scvs(project_root: str):
    """
    Iterates through all SCV worktrees. If the process is no longer running,
    runs cleanup_scv on it.
    """
    worktrees_dir = os.path.join(project_root, ".adjutant", "worktrees")
    if not os.path.exists(worktrees_dir):
        return

    active_scvs = get_active_scvs(project_root)
    found_orphans = []
    
    for entry in os.listdir(worktrees_dir):
        worktree_path = os.path.join(worktrees_dir, entry)
        if os.path.isdir(worktree_path) and not entry.startswith('.'):
            if entry not in active_scvs:
                found_orphans.append(entry)

    if not found_orphans:
        logger.info("No orphaned SCV worktrees found.")
        return

    logger.info(f"Found {len(found_orphans)} orphaned worktree(s). Cleaning up...")
    
    for entry in found_orphans:
        cleanup_scv(entry, project_root)


def run_adjutant_agent(initial_directive: str):
    """
    Launches the Adjutant (Planner) agent as an interactive Gemini session.
    """
    project_root = get_project_root()
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Setup logging to file by default for the interactive session
    log_path = os.path.join(project_root, ".adjutant", "logs", "adjutant.log")
    setup_logging(to_stdout=False, log_file=log_path)

    logger.info("\n[Adjutant Online: Initiating Mission Planning]")
    
    # Recover any orphaned SCVs from previous session
    recover_orphaned_scvs(project_root)

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
    
    sync_overseer = SyncOverseer()
    sync_overseer.start()
    
    try:
        subprocess.run(cmd, env=env, check=False)
    except FileNotFoundError:
        logger.info("Error: 'gemini' CLI not found. Please ensure it is installed and in your PATH.")
        sys.exit(1)
    except Exception as e:
        logger.info(f"Error launching Adjutant: {e}")
        sys.exit(1)
    finally:
        hud.stop()
        overseer.stop()
        sync_overseer.stop()
        if os.path.exists(temp_prompt_path):
            os.remove(temp_prompt_path)


def spawn_agent(agent_name: str, objective_id: str, starting_model: str = None, directive: str = "Execute mission."):
    """
    Spawns a sub-agent asynchronously.
    """
    # Mark the objective as in_progress in bd
    try:
        subprocess.run(["bd", "update", objective_id, "--status", "in_progress"], check=False, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agent_dir = os.path.join(base_dir, "adjutant", "agents", agent_name)
    system_prompt_path = os.path.join(agent_dir, "system.md")
    
    if not os.path.exists(system_prompt_path):
        raise ValueError(f"Unknown agent or missing system prompt: {agent_name}")

    with open(system_prompt_path, "r") as f:
        prompt_template = f.read()
    
    prompt = prompt_template.format(objective_id=objective_id)
    project_root = get_project_root()

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
            ["bd", "worktree", "create", worktree_path, "--branch", branch_name],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"Created worktree at {worktree_path} on branch {branch_name} via 'bd worktree'")
    except subprocess.CalledProcessError as e:
        if "already exists" in e.stderr or "already exists" in e.stdout:
            logger.info(f"Worktree or branch already exists for {objective_id}. Proceeding.")
        else:
            raise RuntimeError(f"Failed to create git worktree: {e.stderr}")

    telemetry_dir = os.path.join(project_root, ".adjutant", "logs")
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
    logger.info(f"--- Spawning sub-agent with model: {model} ---")
    cmd = [
        "gemini", 
        "--model", model, 
        "--policy", policy_dir, 
        "--include-directories", project_root, 
        "--include-directories", os.path.join(project_root, ".beads"), 
        "--include-directories", git_common_dir,
        "--include-directories", git_dir,
        "--yolo", 
        "-p", directive
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

    # Write worktree-local SCV info
    scv_info_path = os.path.join(worktree_path, ".scv_info.json")
    try:
        with open(scv_info_path, "w") as f:
            json.dump({
                "pid": process.pid,
                "agent_name": agent_name,
                "model": model
            }, f, indent=2)
    except IOError as e:
        logger.warning(f"Failed to write .scv_info.json to {scv_info_path}: {e}")

    logger.info(f"Spawned {agent_name} for {objective_id}. Logging to {log_path}")

def show_status():
    """Displays the current status of the Adjutant mission and active SCVs."""
    project_root = get_project_root()
    print("=== Adjutant Status ===")
    
    # Get active mission summary
    try:
        output = subprocess.check_output(["bd", "status", "--json"], cwd=project_root, text=True, stderr=subprocess.DEVNULL)
        status_data = json.loads(output)
        summary = status_data.get("summary", {})
        total = summary.get("total_issues", 0)
        open_issues = summary.get("open_issues", 0)
        closed = summary.get("closed_issues", 0)
        in_progress = summary.get("in_progress_issues", 0)
        
        progress = (closed / total * 100) if total > 0 else 0
        print(f"\nMission Progress: {progress:.1f}% ({closed}/{total} issues closed)")
        print(f"Open: {open_issues} | In Progress: {in_progress}")
    except Exception:
        print("Could not retrieve mission status summary from bd.")

    # List active objectives
    print("\n--- Active Objectives ---")
    try:
        output = subprocess.check_output(["bd", "list", "--json"], cwd=project_root, text=True, stderr=subprocess.DEVNULL)
        objectives = json.loads(output)
        in_progress_objs = [obj for obj in objectives if obj.get("status") == "in_progress"]
        if not in_progress_objs:
            print("No active objectives.")
        else:
            for obj in in_progress_objs:
                print(f"[{obj['id']}] {obj['title']}")
    except Exception:
        print("Could not retrieve active objectives list from bd.")

    # List running SCVs
    print("\n--- Running SCVs ---")
    registry = get_active_scvs(project_root)
    if not registry:
        print("No active SCVs.")
    else:
        for obj_id, info in registry.items():
            pid = info.get("pid", "Unknown")
            agent = info.get("agent_name", "Unknown")
            model = info.get("model", "Unknown")
            print(f"[{obj_id}] Agent: {agent} | PID: {pid} | Status: Running | Model: {model}")
