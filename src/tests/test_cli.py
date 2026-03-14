import sys
from unittest.mock import patch
from adjutant.cli import main

def test_main_with_positional_args():
    # Test with positional arguments
    test_args = ["adjutant", "Initial", "mission", "directive"]
    with patch.object(sys, "argv", test_args):
        with patch("adjutant.cli.run_adjutant_agent") as mock_run:
            main()
            mock_run.assert_called_once_with("Initial mission directive")

def test_main_no_args():
    # Test with no arguments
    test_args = ["adjutant"]
    with patch.object(sys, "argv", test_args):
        with patch("adjutant.cli.run_adjutant_agent") as mock_run:
            main()
            mock_run.assert_called_once_with("I'm ready to assist with a mission.")
