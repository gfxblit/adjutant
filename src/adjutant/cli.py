import argparse
import sys
import os
import subprocess
from adjutant.engine import (
    run_adjutant_agent, 
    spawn_agent, 
    recover_orphaned_scvs, 
    show_status, 
    show_logs,
    setup_logging, 
    get_project_root,
    plan_out_tmux,
    abort_scv,
    cleanup_scv
)
from adjutant.tui import run_tui

def main():
    parser = argparse.ArgumentParser(
        description="Adjutant Autonomous Development Loop. Run with no arguments to start an interactive planning session."
    )
    subparsers = parser.add_subparsers(dest="command")

    # plan subcommand
    plan_parser = subparsers.add_parser("plan", help="Mission planning (default). Accepts an optional mission directive.")
    plan_parser.add_argument("mission", nargs="*", help="Initial mission directive")

    # run-agent subcommand
    run_agent_parser = subparsers.add_parser("run-agent", help="Spawn a sub-agent")
    run_agent_parser.add_argument("agent", help="Agent name (e.g. scv-coder)")
    run_agent_parser.add_argument("objective_id", help="Objective ID to work on")
    run_agent_parser.add_argument("--directive", help="Custom mission directive for the agent")

    # logs subcommand
    logs_parser = subparsers.add_parser("logs", help="Show logs for a mission or SCV")
    logs_parser.add_argument("objective_id", nargs="?", help="Objective ID (e.g. h6z or adjutant-h6z)")
    logs_parser.add_argument("-f", "--follow", action="store_true", help="Follow log output")

    # recover subcommand
    subparsers.add_parser("recover", help="Recover stranded SCV work from orphaned worktrees")

    # status subcommand
    subparsers.add_parser("status", help="Show Adjutant mission and SCV status")

    # abort subcommand
    abort_parser = subparsers.add_parser("abort", help="Abort a running SCV")
    abort_parser.add_argument("objective_id", help="Objective ID to abort")

    # close subcommand
    close_parser = subparsers.add_parser("close", help="Close a mission, committing any stranded work and removing its worktree")
    close_parser.add_argument("objective_id", help="Objective ID to close")

    # tui subcommand
    subparsers.add_parser("tui", help="Launch the Adjutant TUI Dashboard")

    # Handle default 'plan' subcommand for backward compatibility
    # If the first argument is not a known command or help, and there are args, assume 'plan'
    known_commands = list(subparsers.choices.keys()) + ["-h", "--help"]
    if len(sys.argv) > 1 and sys.argv[1] not in known_commands:
        if len(sys.argv) == 2:
            potential_bd_id = sys.argv[1]
            # Heuristic: if it looks like one of our bead IDs, we expect it to be a valid shortcut
            if potential_bd_id.startswith("adjutant-"):
                try:
                    subprocess.run(["bd", "show", potential_bd_id], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    plan_out_tmux(potential_bd_id)
                    sys.exit(0)
                except subprocess.CalledProcessError:
                    print(f"Error: Invalid bead ID '{potential_bd_id}'. No such bead found in database.", file=sys.stderr)
                    sys.exit(1)
            else:
                # For other single arguments, try it as an ID but fallback silently if not found
                try:
                    subprocess.run(["bd", "show", potential_bd_id], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    plan_out_tmux(potential_bd_id)
                    sys.exit(0)
                except subprocess.CalledProcessError:
                    # Fallback to 'plan' subcommand for directives
                    pass
                
        sys.argv.insert(1, "plan")
    
    args = parser.parse_args()

    project_root = get_project_root()
    log_path = os.path.join(project_root, ".adjutant", "logs", "adjutant.log")

    if args.command == "run-agent":
        setup_logging(to_stdout=False, log_file=log_path)
        spawn_kwargs = {}
        if args.directive:
            spawn_kwargs["directive"] = args.directive
        spawn_agent(args.agent, args.objective_id, **spawn_kwargs)
    elif args.command == "abort":
        setup_logging(to_stdout=True, log_file=log_path)
        print(f"Aborting SCV for {args.objective_id}...")
        abort_scv(args.objective_id)
    elif args.command == "close":
        setup_logging(to_stdout=True, log_file=log_path)
        print(f"Closing mission {args.objective_id}...")
        cleanup_scv(args.objective_id, project_root)
        print(f"Mission {args.objective_id} closed.")
    elif args.command == "recover":
        setup_logging(to_stdout=False, log_file=log_path)
        print("Initiating SCV worktree recovery...")
        recover_orphaned_scvs(project_root)
        print("Recovery complete.")
    elif args.command == "status":
        setup_logging(to_stdout=True, log_file=log_path)
        show_status()
    elif args.command == "tui":
        setup_logging(to_stdout=False, log_file=log_path)
        run_tui()
    elif args.command == "logs":
        setup_logging(to_stdout=True, log_file=log_path)
        show_logs(args.objective_id, follow=args.follow)
    else:
        # Default behavior: run the planning agent
        mission_args = getattr(args, "mission", [])
        mission_directive = " ".join(mission_args)
        if not mission_directive:
            mission_directive = "Please provide your mission directive or ask for status/help."
        run_adjutant_agent(mission_directive)

if __name__ == "__main__":
    main()
