import unittest
from unittest.mock import patch, mock_open, MagicMock
import json
import time
import os
from adjutant.engine import AdjutantHUD, run_adjutant_agent

class TestAdjutantHUD(unittest.TestCase):
    @patch("subprocess.check_output")
    @patch("sys.stdout.write")
    @patch("sys.stdout.flush")
    @patch("os.path.exists")
    def test_update_hud_success(self, mock_exists, mock_flush, mock_write, mock_check_output):
        # Mock 'bd status --json' output
        mock_check_output.return_value = json.dumps({
            "summary": {
                "total_issues": 10,
                "open_issues": 3,
                "closed_issues": 7,
                "in_progress_issues": 0
            }
        }).encode()
        
        # Mock registry doesn't exist for now
        mock_exists.return_value = False
        
        hud = AdjutantHUD(mission="Test Mission")
        hud.update_hud()
        
        # Updated expected format: Mission: {MISSION} | {PROGRESS}% | {CLOSED}/{TOTAL} | Open: {OPEN}, IP: {IN_PROGRESS}
        expected_title = "\033]0;Mission: Test Mission | 70.0% | 7/10 | Open: 3, IP: 0\007"
        mock_write.assert_called_with(expected_title)
        mock_flush.assert_called()

    @patch("subprocess.check_output")
    @patch("sys.stdout.write")
    @patch("os.path.exists")
    def test_update_hud_handles_subprocess_error(self, mock_exists, mock_write, mock_check_output):
        import subprocess
        mock_check_output.side_effect = subprocess.CalledProcessError(1, ["bd", "status", "--json"])
        mock_exists.return_value = False
        
        hud = AdjutantHUD(mission="Test Mission")
        # Should not raise exception
        hud.update_hud()
        # It still writes the title, just with 0% progress if bd fails
        expected_title = "\033]0;Mission: Test Mission | 0.0% | 0/0 | Open: 0, IP: 0\007"
        mock_write.assert_called_with(expected_title)

    @patch("adjutant.engine.get_active_scvs")
    @patch("subprocess.check_output")
    @patch("sys.stdout.write")
    def test_update_hud_with_scvs(self, mock_write, mock_check_output, mock_get_scvs):
        # Mock 'bd status --json' output
        mock_check_output.return_value = json.dumps({
            "summary": {
                "total_issues": 10,
                "open_issues": 3,
                "closed_issues": 7,
                "in_progress_issues": 0
            }
        }).encode()
        
        # Mock get_active_scvs
        mock_get_scvs.return_value = {
            "adjutant-sjz.3": {"pid": 123},
            "adjutant-sjz.4": {"pid": 456}
        }
        
        hud = AdjutantHUD(mission="Test Mission")
        hud.update_hud()
        
        # Expected title with SCVs: ... | SCVs: 2 (sjz.3, sjz.4)
        expected_title = "\033]0;Mission: Test Mission | 70.0% | 7/10 | Open: 3, IP: 0 | SCVs: 2 (sjz.3, sjz.4)\007"
        mock_write.assert_called_with(expected_title)

    @patch("adjutant.engine.get_active_scvs")
    @patch("subprocess.check_output")
    @patch("sys.stdout.write")
    def test_update_hud_edge_cases(self, mock_write, mock_check_output, mock_get_scvs):
        mock_get_scvs.return_value = {}
        hud = AdjutantHUD(mission="Test Mission")

        # Case 1: 0 issues
        mock_check_output.return_value = json.dumps({
            "summary": {"total_issues": 0, "open_issues": 0, "closed_issues": 0, "in_progress_issues": 0}
        }).encode()
        hud.update_hud()
        mock_write.assert_called_with("\033]0;Mission: Test Mission | 0.0% | 0/0 | Open: 0, IP: 0\007")

        # Case 2: 100% closed
        mock_check_output.return_value = json.dumps({
            "summary": {"total_issues": 5, "open_issues": 0, "closed_issues": 5, "in_progress_issues": 0}
        }).encode()
        hud.update_hud()
        mock_write.assert_called_with("\033]0;Mission: Test Mission | 100.0% | 5/5 | Open: 0, IP: 0\007")

    def test_hud_thread_lifecycle(self):
        with patch("adjutant.engine.AdjutantHUD.update_hud") as mock_update:
            hud = AdjutantHUD(mission="Test", interval=0.1)
            hud.start()
            self.assertTrue(hud.thread.is_alive())
            
            # Wait a bit for at least one update
            time.sleep(0.2)
            self.assertTrue(mock_update.called)
            
            hud.stop()
            self.assertFalse(hud.thread.is_alive())

class TestRunAdjutantAgent(unittest.TestCase):
    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    @patch("adjutant.engine.AdjutantHUD")
    @patch("adjutant.engine.SCVOverseer")
    @patch("adjutant.engine.recover_orphaned_scvs")
    @patch("adjutant.engine.setup_logging")
    def test_run_adjutant_agent_uses_static_prompt(self, mock_setup_logging, mock_recover, mock_overseer_class, mock_hud_class, mock_remove, mock_exists, mock_run):
        mock_exists.return_value = True
        directive = "Test mission"
        
        # In the new version, we don't need to mock open for the system prompt
        # but we still want to ensure setup_logging and recover_orphaned_scvs are called.
        run_adjutant_agent(directive)
        
        # Verify subprocess.run was called with correct environment
        self.assertTrue(mock_run.called)
        args, kwargs = mock_run.call_args
        env = kwargs.get("env")
        self.assertIsNotNone(env)
        self.assertTrue(env["GEMINI_SYSTEM_MD"].endswith("adjutant/agents/adjutant/system.md"))


    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    @patch("adjutant.engine.AdjutantHUD")
    @patch("adjutant.engine.SCVOverseer")
    @patch("adjutant.engine.recover_orphaned_scvs")
    @patch("adjutant.engine.setup_logging")
    def test_run_adjutant_agent_hud_integration(self, mock_setup_logging, mock_recover, mock_overseer_class, mock_hud_class, mock_remove, mock_exists, mock_run):
        mock_exists.return_value = True
        mock_hud_instance = mock_hud_class.return_value
        
        run_adjutant_agent("Test")
        
        mock_hud_class.assert_called_once_with(mission="Test")
        mock_hud_instance.start.assert_called_once()
        mock_hud_instance.stop.assert_called_once()
        mock_recover.assert_called_once()

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    @patch("adjutant.engine.AdjutantHUD")
    @patch("adjutant.engine.SCVOverseer")
    @patch("adjutant.engine.recover_orphaned_scvs")
    @patch("adjutant.engine.setup_logging")
    @patch("adjutant.engine.logger")
    def test_run_adjutant_agent_gemini_not_found(self, mock_logger, mock_setup_logging, mock_recover, mock_overseer_class, mock_hud_class, mock_remove, mock_exists, mock_run):
        mock_exists.return_value = True
        mock_run.side_effect = FileNotFoundError()
        
        with patch("sys.exit") as mock_exit:
            # Mocking open to avoid file system interaction
            with patch("builtins.open", mock_open(read_data="template")):
                run_adjutant_agent("Test")
        
        mock_exit.assert_called_with(1)
        mock_logger.info.assert_any_call("Error: 'gemini' CLI not found. Please ensure it is installed and in your PATH.")
        mock_recover.assert_called_once()

if __name__ == "__main__":
    unittest.main()
