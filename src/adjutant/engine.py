import os
import subprocess
import sys
import signal
import threading
import json
import logging
import shlex
import re
from datetime import datetime, timezone
from typing import Optional

# Setup logger
logger = logging.getLogger("adjutant")

TMUX_SESSION_PREFIX = "epic--"


def format_duration(iso_date: str) -> str:
    """Formats the duration from iso_date until now as a short string (e.g., 2h15m)."""
    if not iso_date or not isinstance(iso_date, str):
        return "???"
    try:
        # datetime.fromisoformat in older versions of Python doesn't handle 'Z' well.
        # Python 3.11+ does, but for safety we replace Z with +00:00.
        dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        duration = now - dt
        seconds = int(duration.total_seconds())
        if seconds < 0:
            return "0s"
        
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        
        if days > 0:
            return f"{days}d{hours}h"
        if hours > 0:
            return f"{hours}h{minutes}m"
        if minutes > 0:
            return f"{minutes}m"
        return f"{seconds}s"
    except (ValueError, TypeError):
        return "???"

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
            directive = scv_info.get("directive", "Execute mission.") # Get original directive
            
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
                                spawn_agent(agent_name, objective_id, starting_model=next_model, directive=directive)
                                continue 
                            else:
                                logger.warning(f"[Overseer] All fallback models exhausted for {objective_id}. Not restarting. Resetting status to open.")
                                try:
                                    subprocess.run(["bd", "update", objective_id, "--status", "open"], check=False, capture_output=True)
                                except Exception:
                                    pass
                                should_restart = False
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


def cleanup_scv(objective_id: str, project_root: str):
    """
    Cleans up the git worktree and pushes the branch to origin.
    Added more robust error handling and logging.
    """
    worktrees_dir = os.path.join(project_root, ".adjutant", "worktrees")
    worktree_path = os.path.join(worktrees_dir, objective_id)
    branch_name = f"scv/{objective_id}"

    logger.info(f"\n[Cleaning up SCV for {objective_id}]")

    # 1. Check if worktree exists before proceeding
    if not os.path.exists(worktree_path):
        logger.info(f"Worktree for {objective_id} does not exist at {worktree_path}. Skipping cleanup.")
        return

    # 2. Auto-commit any pending changes in the worktree
    try:
        # Use check=True for git add to ensure staging errors are caught.
        subprocess.run(["git", "add", "."], cwd=worktree_path, check=True, capture_output=True)
        logger.debug(f"Staged all changes in {worktree_path}.")

        # Commit with check=False because 'nothing to commit' is a valid, non-error state.
        res = subprocess.run(
            ["git", "commit", "-m", f"Auto-commit stranded work for {objective_id}"],
            cwd=worktree_path,
            check=False,
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            logger.info(f"Auto-committed any stranded changes in {worktree_path}.")
        elif "nothing to commit" not in (res.stdout + res.stderr).lower():
            # Log as an error if the exit code is non-zero and it's not the "nothing to commit" message.
            logger.error(f"Failed to auto-commit in {worktree_path} (exit code {res.returncode}): {res.stderr.strip()}")
        else:
            logger.debug("No new changes to commit.")
    except subprocess.CalledProcessError as e:
        # Log detailed error if git add fails.
        logger.error(f"Error staging changes in {worktree_path}: {e.stderr.strip()}")
    except Exception as e:
        # Catch any other unexpected errors during the auto-commit process.
        logger.error(f"An unexpected error occurred during auto-commit for {worktree_path}: {e}")

    # 3. Push the branch
    try:
        res = subprocess.run(
            ["git", "push", "origin", branch_name],
            cwd=project_root,
            check=False, # Do not fail script if push fails, just log it.
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            logger.info(f"Pushed branch {branch_name} to origin.")
        else:
            # Log error with stderr content for clarity on push failure.
            logger.error(f"Failed to push branch {branch_name} (exit code {res.returncode}): {res.stderr.strip()}")
    except Exception as e:
        # Catch any other unexpected errors during the git push process.
        logger.error(f"An unexpected error occurred during git push for {branch_name}: {e}")

    # 4. Remove the worktree
    if os.path.exists(worktree_path):
        try:
            # Use --force because we already attempted to commit/push above,
            # and we want to ensure the worktree is actually removed.
            subprocess.run(["bd", "worktree", "remove", objective_id, "--force"], cwd=project_root, check=True, capture_output=True)
            logger.info(f"Removed worktree for {objective_id} via 'bd worktree remove --force'.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to remove worktree for {objective_id}: {e.stderr.decode().strip()}")
        except Exception as e:
            logger.error(f"Unexpected error removing worktree for {objective_id}: {e}")


def abort_scv(objective_id: str):
    """
    Terminates a running SCV process and performs cleanup.
    """
    project_root = get_project_root()
    active_scvs = get_active_scvs(project_root)
    
    if objective_id not in active_scvs:
        logger.warning(f"No active SCV found for objective {objective_id}. Attempting cleanup of orphaned worktree.")
        # Still attempt cleanup in case the process died but worktree remains
        cleanup_scv(objective_id, project_root)
        return

    scv_info = active_scvs[objective_id]
    pid = scv_info.get("pid")
    
    if pid:
        logger.info(f"Terminating SCV for {objective_id} (PID: {pid})...")
        try:
            # First try a clean SIGTERM to the process group.
            # We use the PGID because SCVs are started with start_new_session=True.
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            logger.info(f"Sent SIGTERM to process group {pgid} for {objective_id}.")
        except ProcessLookupError:
            logger.warning(f"Process {pid} or process group not found.")
        except Exception as e:
            logger.error(f"Failed to terminate process {pid}: {e}")

    # Mark the objective as open in bd to allow restart
    try:
        subprocess.run(["bd", "update", objective_id, "--status", "open"], check=False, capture_output=True)
        logger.info(f"Reset objective {objective_id} status to 'open'.")
    except Exception:
        pass



    # Run cleanup (which commits, pushes, and removes worktree)
    cleanup_scv(objective_id, project_root)


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


def plan_out_tmux(bd_id: str):
    """Starts an interactive planning session for a specific bead in a tmux session."""
    try:
        output = subprocess.check_output(["bd", "show", bd_id, "--json"], text=True)
        bd_data = json.loads(output)
        if isinstance(bd_data, list) and len(bd_data) > 0:
            bd_data = bd_data[0]
        title = bd_data.get("title", "planning")
    except (subprocess.CalledProcessError, json.JSONDecodeError, AttributeError, IndexError):
        title = "planning"

    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    if not slug:
        slug = "planning"

    session_name = f"{TMUX_SESSION_PREFIX}{bd_id}"
    
    # Check if session already exists
    session_exists = False
    try:
        subprocess.run(["tmux", "has-session", "-t", session_name], check=True, capture_output=True)
        session_exists = True
    except FileNotFoundError:
        logger.error("tmux not found. Please install tmux to use this feature.")
        sys.exit(1)
    except subprocess.CalledProcessError:
        pass # Session doesn't exist, create it

    if session_exists:
        os.execvp("tmux", ["tmux", "attach-session", "-t", session_name])
    else:
        try:
            # Create detached session
            subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "-n", slug[:50]], check=True)
            
            # Send keys to window 0
            planner_directive = f"Activate the planner skill. Read bead {bd_id} and clarify requirements with me."
            gemini_cmd_parts = [
                "gemini",
                "--allowed-tools", "run_shell_command,activate_skill",
                "-i", planner_directive
            ]
            cmd = f"{shlex.join(gemini_cmd_parts)}\n"
            subprocess.run(["tmux", "send-keys", "-t", f"{session_name}:0", cmd], check=True)
            
            # Attach to the session
            os.execvp("tmux", ["tmux", "attach-session", "-t", session_name])
        except (subprocess.CalledProcessError, OSError) as e:
            logger.error(f"Failed to start tmux session: {e}")
            sys.exit(1)


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
    
    env = os.environ.copy()
    env["GEMINI_SYSTEM_MD"] = system_prompt_path
    
    policy_dir = os.path.join(adjutant_agent_dir, "policies")
    cmd = ["gemini", "--model", "gemini-3.1-pro-preview", "--policy", policy_dir, "-i", initial_directive]
    
    hud = AdjutantHUD(mission=initial_directive)
    hud.start()

    overseer = SCVOverseer()
    overseer.start()
    
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


def spawn_agent(agent_name: str, objective_id: str, starting_model: str = None, directive: str = "Execute mission."):
    """
    Spawns a sub-agent asynchronously.
    """
    # Mark the objective as in_progress in bd
    try:
        subprocess.run(["bd", "update", objective_id, "--status", "in_progress"], check=False, capture_output=True)
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agent_dir = os.path.join(base_dir, "adjutant", "agents", agent_name)
    system_prompt_path = os.path.join(agent_dir, "system.md")
    
    if not os.path.exists(system_prompt_path):
        raise ValueError(f"Unknown agent or missing system prompt: {agent_name}")

    with open(system_prompt_path, "r") as f:
        system_prompt_content = f.read()
    
    initial_prompt = f"Objective ID: {objective_id}\n\n{directive}"
    project_root = get_project_root()

    worktrees_dir = os.path.join(project_root, ".adjutant", "worktrees")
    os.makedirs(worktrees_dir, exist_ok=True)
    worktree_path = os.path.join(worktrees_dir, objective_id)
    branch_name = f"scv/{objective_id}"

    env = os.environ.copy()
    env["ADJUTANT_DISABLE_HOOK"] = "1"
    
    env["GEMINI_SYSTEM_MD"] = system_prompt_path
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

    # Ensure the SCV can use the 'bd' CLI by creating a .beads/redirect
    try:
        beads_redirect_dir = os.path.join(worktree_path, ".beads")
        os.makedirs(beads_redirect_dir, exist_ok=True)
        beads_redirect_path = os.path.join(beads_redirect_dir, "redirect")
        with open(beads_redirect_path, "w") as f:
            f.write(os.path.join(project_root, ".beads"))
        logger.info("Created .beads/redirect pointing to main database.")
    except Exception as e:
        logger.warning(f"Failed to create .beads/redirect for {objective_id}: {e}")

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
    
    in_tmux = "TMUX" in os.environ
    if in_tmux:
        # When running inside a tmux session, we want it interactive and in a new window
        cmd_flag = "-i"
    else:
        cmd_flag = "-p"

    cmd = [
        "gemini", 
        "--model", model, 
        "--policy", policy_dir, 
        "--include-directories", project_root, 
        "--include-directories", os.path.join(project_root, ".beads"), 
        "--include-directories", git_common_dir,
        "--include-directories", git_dir,
        "--yolo", 
        cmd_flag, initial_prompt
    ]
    
    # Log system prompt and command to the objective's log file
    with open(log_path, "a") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"SCV SPAWN: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"AGENT: {agent_name}\n")
        f.write(f"MODEL: {model}\n")
        f.write(f"{'-'*80}\n")
        f.write("SYSTEM PROMPT:\n")
        f.write(system_prompt_content)
        f.write(f"\n{'-'*80}\n")
        f.write("COMMAND:\n")
        f.write(shlex.join(cmd))
        f.write(f"\n{'='*80}\n\n")

    process_pid = None

    if in_tmux:
        logger.info(f"Spawning SCV {objective_id} in new tmux window (Interactive)...")
        env_vars = f"GEMINI_SYSTEM_MD={shlex.quote(system_prompt_path)} ADJUTANT_DISABLE_HOOK=1"
        gemini_cmd_str = shlex.join(cmd)
        
        tmux_target_cmd = f"cd {shlex.quote(worktree_path)} && env {env_vars} {gemini_cmd_str}"
        
        tmux_cmd = [
            "tmux", "new-window", 
            "-P", "-F", "#{pane_pid}",
            "-n", f"task-{objective_id}", 
            tmux_target_cmd
        ]
        
        try:
            output = subprocess.check_output(tmux_cmd, env=env, stderr=subprocess.STDOUT, text=True).strip()
            if output.isdigit():
                process_pid = int(output)
            else:
                logger.warning(f"Failed to parse PID from tmux output: {output}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to spawn tmux window: {e.output.strip() if hasattr(e, 'output') and e.output else e}")
            logger.info("Falling back to standard background execution...")
            in_tmux = False

    if not in_tmux:
        log_file = open(log_path, "a")
        process = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            cwd=worktree_path,
            env=env,
            start_new_session=True
        )
        process_pid = process.pid
        log_file.close()

    # Write worktree-local SCV info
    if process_pid:
        scv_info_path = os.path.join(worktree_path, ".scv_info.json")
        try:
            with open(scv_info_path, "w") as f:
                json.dump({
                    "pid": process_pid,
                    "agent_name": agent_name,
                    "model": model, 
                    "directive": directive,
                    "start_time": datetime.now(timezone.utc).isoformat(),
                    "in_tmux": in_tmux
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write .scv_info.json to {scv_info_path}: {e}")

    logger.info(f"Spawned {agent_name} for {objective_id}. PID: {process_pid}. Logging to {log_path}")

def show_status():
    """Displays the current status of the Adjutant mission and active SCVs."""
    project_root = get_project_root()
    
    # 1. Mission Progress from 'bd status'
    try:
        output = subprocess.check_output(["bd", "status", "--json"], cwd=project_root, text=True, stderr=subprocess.DEVNULL)
        status_data = json.loads(output)
        summary = status_data.get("summary", {})
        total = summary.get("total_issues", 0)
        open_issues = summary.get("open_issues", 0)
        closed = summary.get("closed_issues", 0)
        in_progress = summary.get("in_progress_issues", 0)
        blocked = summary.get("blocked_issues", 0)
        
        progress = (closed / total * 100) if total > 0 else 0
        print(f"📊 Adjutant Mission: {progress:.1f}% ({closed}/{total} closed)")
        print(f"   Status: ○ {open_issues} open | ◐ {in_progress} in progress | ● {blocked} blocked | ✓ {closed} closed")
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        print("Could not retrieve mission status summary from bd.")

    # 2. Unified Active Objectives and SCVs
    print("\nActive Objectives:")
    registry = get_active_scvs(project_root)
    
    try:
        # Use 'bd list --status in_progress --json' to get active objectives
        output = subprocess.check_output(["bd", "list", "--status", "in_progress", "--json"], cwd=project_root, text=True, stderr=subprocess.DEVNULL)
        objectives = json.loads(output)
        
        ip_ids = {obj["id"] for obj in objectives}
        titles = {obj["id"]: obj["title"] for obj in objectives}
        updated_ats = {obj["id"]: obj.get("updated_at") for obj in objectives}
        
        # Combine IDs from bd and running SCVs
        all_ids = sorted(ip_ids | registry.keys())
        
        if not all_ids:
            print("  (None)")
        else:
            for obj_id in all_ids:
                title = titles.get(obj_id, "Unknown Objective")
                
                scv_info_str = ""
                time_info = ""
                
                # Determine duration from start_time (best) or updated_at (fallback)
                scv_info = registry.get(obj_id, {})
                best_ts = scv_info.get("start_time") or updated_ats.get(obj_id)
                duration = format_duration(best_ts) if best_ts else None

                if obj_id in registry:
                    agent = scv_info.get("agent_name", "???")
                    pid = scv_info.get("pid", "???")
                    run_suffix = f": {duration}" if duration and duration != "???" else ""
                    scv_info_str = f" [{agent} | PID: {pid} | Running{run_suffix}]"
                elif duration and duration != "???":
                    time_info = f" (In progress: {duration})"
                
                status_icon = "◐" if obj_id in ip_ids else "⚠️"
                print(f"  {status_icon} {obj_id}: {title}{time_info}{scv_info_str}")
                
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        # Fallback if bd list fails but we have SCV info
        if registry:
            for obj_id, info in registry.items():
                agent = info.get("agent_name", "???")
                pid = info.get("pid", "???")
                start_time = info.get("start_time")
                duration = format_duration(start_time) if start_time else None
                run_suffix = f": {duration}" if duration and duration != "???" else ""
                print(f"  ? {obj_id}: [SCV Running] [{agent} | PID: {pid} | Running{run_suffix}]")
        else:
            print("  (None)")

def show_logs(objective_id: Optional[str] = None, follow: bool = False):
    """Shows the logs for a given objective or the main adjutant log."""
    project_root = get_project_root()
    log_dir = os.path.join(project_root, ".adjutant", "logs")
    
    if not objective_id:
        log_path = os.path.join(log_dir, "adjutant.log")
    else:
        # Try exact match first
        log_path = os.path.join(log_dir, f"{objective_id}.log")
        if not os.path.exists(log_path):
            # Try with adjutant- prefix if not present
            if not objective_id.startswith("adjutant-"):
                alt_path = os.path.join(log_dir, f"adjutant-{objective_id}.log")
                if os.path.exists(alt_path):
                    log_path = alt_path
    
    if not os.path.exists(log_path):
        print(f"No logs found at {log_path}")
        return

    if follow:
        try:
            import shutil
            # Use tail -f if available, otherwise a simple loop
            if shutil.which("tail"):
                subprocess.run(["tail", "-f", log_path])
            else:
                import time
                with open(log_path, "r") as f:
                    # Go to the end of file
                    f.seek(0, os.SEEK_END)
                    while True:
                        line = f.readline()
                        if not line:
                            time.sleep(0.1)
                            continue
                        print(line, end="")
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"Error following logs: {e}")
    else:
        try:
            with open(log_path, "r") as f:
                # For large logs, maybe we only want the last N lines?
                # But typically 'logs' shows everything unless tail is specified.
                # However, for an agent log, it can be huge.
                # Let's just print it all for now, as it's common for CLI logs.
                print(f.read())
        except Exception as e:
            print(f"Error reading logs: {e}")
