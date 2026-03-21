import argparse
import sys
import os
import subprocess
from adjutant.engine import run_adjutant_agent, spawn_agent, recover_orphaned_scvs
from adjutant.ui import run_ui

def main():
    parser = argparse.ArgumentParser(description="Adjutant Autonomous Development Loop")
    subparsers = parser.add_subparsers(dest="command")

    # plan subcommand
    plan_parser = subparsers.add_parser("plan", help="Mission planning (default)")
    plan_parser.add_argument("mission", nargs="*", help="Initial mission directive")

    # ui subcommand
    ui_parser = subparsers.add_parser("ui", help="Run the Adjutant HUD")
    ui_parser.add_argument("mission", nargs="*", help="Mission directive to display in HUD")

    # run-agent subcommand
    run_agent_parser = subparsers.add_parser("run-agent", help="Spawn a sub-agent")
    run_agent_parser.add_argument("agent", help="Agent name (e.g. scv-coder)")
    run_agent_parser.add_argument("objective_id", help="Objective ID to work on")

    # recover subcommand
    recover_parser = subparsers.add_parser("recover", help="Trigger bulk recovery of orphaned SCV worktrees")
    recover_parser.add_argument("--objective", help="Recover a specific objective ID")
    recover_parser.add_argument("--dry-run", action="store_true", help="List what would be recovered without doing it")

    # Handle default 'plan' subcommand for backward compatibility
    if len(sys.argv) > 1 and sys.argv[1] not in ["plan", "ui", "run-agent", "recover", "-h", "--help"]:
        # If the first argument is not a known command or help, assume 'plan'
        sys.argv.insert(1, "plan")
    
    args = parser.parse_args()

    # Find project root (handle worktrees)
    try:
        project_root = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], stderr=subprocess.DEVNULL, text=True).strip()
        if project_root.endswith(".git"):
            project_root = os.path.dirname(project_root)
        project_root = os.path.abspath(project_root)
    except subprocess.CalledProcessError:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(base_dir)

    if args.command == "run-agent":
        spawn_agent(args.agent, args.objective_id)
    elif args.command == "recover":
        from adjutant.engine import cleanup_scv
        if args.objective:
            if args.dry_run:
                print(f"[Dry Run] Would recover specific objective: {args.objective}")
            else:
                cleanup_scv(args.objective, project_root)
        else:
            recover_orphaned_scvs(project_root, dry_run=args.dry_run)
    elif args.command == "ui":
        mission_args = getattr(args, "mission", [])
        mission_directive = " ".join(mission_args)
        if not mission_directive:
            mission_directive = "Active Mission"
        run_ui(mission_directive)
    else:
        # If no command, it's 'plan' (either explicit or implicit)
        # mission attribute only exists if 'plan' subcommand was used (explicitly or implicitly via insertion)
        mission_args = getattr(args, "mission", [])
        mission_directive = " ".join(mission_args)
        if not mission_directive:
            mission_directive = "I'm ready to assist with a mission."
        run_adjutant_agent(mission_directive)

if __name__ == "__main__":
    main()
