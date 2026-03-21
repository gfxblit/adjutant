import argparse
import sys
import os
from adjutant.engine import run_adjutant_agent, spawn_agent, recover_orphaned_scvs, show_status
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
    run_agent_parser.add_argument("--directive", help="Custom mission directive for the agent")

    # recover subcommand
    subparsers.add_parser("recover", help="Recover stranded SCV work from orphaned worktrees")

    # status subcommand
    subparsers.add_parser("status", help="Show Adjutant mission and SCV status")

    # Handle default 'plan' subcommand for backward compatibility
    if len(sys.argv) > 1 and sys.argv[1] not in ["plan", "ui", "run-agent", "recover", "status", "-h", "--help"]:
        # If the first argument is not a known command or help, assume 'plan'
        sys.argv.insert(1, "plan")
    
    args = parser.parse_args()

    if args.command == "run-agent":
        spawn_kwargs = {}
        if args.directive:
            spawn_kwargs["directive"] = args.directive
        spawn_agent(args.agent, args.objective_id, **spawn_kwargs)
    elif args.command == "recover":
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        project_root = os.path.dirname(base_dir)
        print("Initiating SCV worktree recovery...")
        recover_orphaned_scvs(project_root)
        print("Recovery complete.")
    elif args.command == "status":
        show_status()
    elif args.command == "ui":
        mission_args = getattr(args, "mission", [])
        mission_directive = " ".join(mission_args)
        if not mission_directive:
            mission_directive = "Active Mission"
        run_ui(mission_directive)
    else:
        # If no command, it's 'plan' (either explicit or implicit)
        mission_args = getattr(args, "mission", [])
        mission_directive = " ".join(mission_args)
        if not mission_directive:
            mission_directive = "I'm ready to assist with a mission."
        run_adjutant_agent(mission_directive)

if __name__ == "__main__":
    main()
