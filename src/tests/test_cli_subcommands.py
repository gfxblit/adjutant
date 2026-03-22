import sys
from unittest.mock import patch
from adjutant.cli import main

def test_plan_subcommand():
    # Test 'plan' subcommand with mission
    test_args = ["adjutant", "plan", "Build", "a", "base"]
    with patch.object(sys, "argv", test_args):
        with patch("adjutant.cli.run_adjutant_agent") as mock_run:
            main()
            mock_run.assert_called_once_with("Build a base")

def test_plan_subcommand_no_mission():
    # Test 'plan' subcommand with no mission
    test_args = ["adjutant", "plan"]
    with patch.object(sys, "argv", test_args):
        with patch("adjutant.cli.run_adjutant_agent") as mock_run:
            main()
            mock_run.assert_called_once_with("I'm ready to assist with a mission.")

def test_default_is_plan():
    # Test default (no subcommand) is 'plan'
    test_args = ["adjutant", "Build", "a", "base"]
    with patch.object(sys, "argv", test_args):
        with patch("adjutant.cli.run_adjutant_agent") as mock_run:
            main()
            mock_run.assert_called_once_with("Build a base")

def test_run_agent_subcommand():
    # Test 'run-agent' subcommand
    test_args = ["adjutant", "run-agent", "scv-coder", "adjutant-123"]
    with patch.object(sys, "argv", test_args):
        # We need to mock it where it's imported in cli.py or from engine
        with patch("adjutant.cli.spawn_agent") as mock_spawn:
            with patch("adjutant.cli.setup_logging") as mock_setup_logging:
                with patch("adjutant.cli.get_project_root") as mock_get_root:
                    mock_get_root.return_value = "/tmp/project"
                    main()
                    mock_spawn.assert_called_once_with("scv-coder", "adjutant-123")
                    mock_setup_logging.assert_called_once_with(
                        to_stdout=False, 
                        log_file="/tmp/project/.adjutant/logs/adjutant.log"
                    )
