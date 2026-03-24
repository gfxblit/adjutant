import sys
from unittest.mock import patch, MagicMock
import os
from adjutant.cli import main
from adjutant.engine import show_logs


def test_logs_command_calls_show_logs():
    test_args = ["adjutant", "logs", "h6z"]
    with patch.object(sys, "argv", test_args):
        with patch("adjutant.cli.show_logs") as mock_show_logs:
            with patch("adjutant.cli.setup_logging"):
                main()
                mock_show_logs.assert_called_once_with("h6z", follow=False)


def test_logs_command_no_args_calls_show_logs():
    test_args = ["adjutant", "logs"]
    with patch.object(sys, "argv", test_args):
        with patch("adjutant.cli.show_logs") as mock_show_logs:
            with patch("adjutant.cli.setup_logging"):
                main()
                mock_show_logs.assert_called_once_with(None, follow=False)


def test_logs_command_follow_calls_show_logs():
    test_args = ["adjutant", "logs", "h6z", "-f"]
    with patch.object(sys, "argv", test_args):
        with patch("adjutant.cli.show_logs") as mock_show_logs:
            with patch("adjutant.cli.setup_logging"):
                main()
                mock_show_logs.assert_called_once_with("h6z", follow=True)


@patch("adjutant.engine.get_project_root")
@patch("os.path.exists")
@patch("builtins.open")
def test_show_logs_reads_file(mock_open, mock_exists, mock_root):
    mock_root.return_value = "/root"
    mock_exists.return_value = True
    mock_file = MagicMock()
    mock_file.read.return_value = "log content"
    mock_open.return_value.__enter__.return_value = mock_file

    with patch("builtins.print") as mock_print:
        show_logs("h6z")
        # Check if the correct log path was used
        expected_path = os.path.join("/root", ".adjutant", "logs", "h6z.log")
        mock_open.assert_called_with(expected_path, "r")
        mock_print.assert_called_once_with("log content")
