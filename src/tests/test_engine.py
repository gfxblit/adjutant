import unittest
from unittest.mock import patch, MagicMock
import os
import json
import time
from adjutant.engine import run_adjutant_agent

class TestEngine(unittest.TestCase):
    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    @patch("builtins.open", new_callable=unittest.mock.mock_open, read_data="# Adjutant System\n${SubAgents}\n${AgentSkills}")
    def test_run_adjutant_agent_calls_gemini_correctly(self, mock_open, mock_remove, mock_exists, mock_run):
        mock_exists.return_value = True
        directive = "Test mission"
        
        run_adjutant_agent(directive)
        
        # Check if subprocess.run was called with correct arguments
        # We expect gemini -i "Test mission"
        args, kwargs = mock_run.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], "gemini")
        self.assertEqual(cmd[1], "-i")
        self.assertEqual(cmd[2], "Test mission")
        
        # Check if GEMINI_SYSTEM_MD was set in env
        env = kwargs.get("env")
        self.assertIsNotNone(env)
        self.assertIn("GEMINI_SYSTEM_MD", env)
        self.assertTrue(env["GEMINI_SYSTEM_MD"].endswith(".adjutant_resolved_system.md"))

class TestAdjutantHUD(unittest.TestCase):
    @patch("subprocess.check_output")
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    def test_update_hud_correctly_formats_title(self, mock_flush, mock_write, mock_check_output):
        # Mock 'bd status --json' output
        mock_check_output.return_value = json.dumps({
            "summary": {
                "total_issues": 10,
                "open_issues": 3,
                "closed_issues": 7,
                "in_progress_issues": 0
            }
        }).encode()
        
        from adjutant.engine import AdjutantHUD
        hud = AdjutantHUD(mission="Test Mission")
        
        # Test the update_hud method
        hud.update_hud()
        
        # Expected title string with ANSI escape sequence
        # Title: Mission: Test Mission | 70% | Open: 3, Closed: 7
        expected_title = "\033]0;Mission: Test Mission | 70.0% | Open: 3, Closed: 7\007"
        mock_write.assert_called_with(expected_title)
        mock_flush.assert_called()

if __name__ == "__main__":
    unittest.main()
