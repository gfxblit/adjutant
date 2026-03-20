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

    @patch("subprocess.check_output")
    @patch("sys.stdout.write")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_update_hud_with_scvs(self, mock_open_file, mock_exists, mock_write, mock_check_output):
        # Mock 'bd status --json' output
        mock_check_output.return_value = json.dumps({
            "summary": {
                "total_issues": 10,
                "open_issues": 3,
                "closed_issues": 7,
                "in_progress_issues": 0
            }
        }).encode()
        
        # Mock registry exists and has SCVs
        registry_data = {
            "adjutant-sjz.3": {"pid": 123},
            "adjutant-sjz.4": {"pid": 456}
        }
        
        def exists_side_effect(path):
            if "active_scvs.json" in path:
                return True
            return False
            
        mock_exists.side_effect = exists_side_effect
        mock_open_file.return_value.__enter__.return_value.read.return_value = json.dumps(registry_data)
        
        hud = AdjutantHUD(mission="Test Mission")
        hud.update_hud()
        
        # Expected title with SCVs: ... | SCVs: 2 (sjz.3, sjz.4)
        expected_title = "\033]0;Mission: Test Mission | 70.0% | 7/10 | Open: 3, IP: 0 | SCVs: 2 (sjz.3, sjz.4)\007"
        mock_write.assert_called_with(expected_title)

    @patch("subprocess.check_output")
    @patch("sys.stdout.write")
    @patch("os.path.exists")
    def test_update_hud_edge_cases(self, mock_exists, mock_write, mock_check_output):
        mock_exists.return_value = False
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
    def test_run_adjutant_agent_writes_resolved_prompt(self, mock_overseer_class, mock_hud_class, mock_remove, mock_exists, mock_run):
        mock_exists.return_value = True
        directive = "Test mission"
        
        # We need to mock open to return our template and then capture what is written to the resolved file
        template_content = "System: Content without placeholders"
        
        # Create a mock for the file handle
        m = mock_open(read_data=template_content)
        
        with patch("builtins.open", m):
            run_adjutant_agent(directive)
        
        # The first call to open is for reading the system prompt
        # The second call is for writing the resolved prompt
        
        self.assertEqual(m.call_count, 2)
        
        # Check path of first open (read)
        read_path = m.call_args_list[0][0][0]
        self.assertTrue(read_path.endswith("adjutant/agents/adjutant/system.md"))
        
        # Check path of second open (write)
        write_path = m.call_args_list[1][0][0]
        self.assertTrue(write_path.endswith(".adjutant_resolved_system.md"))
        self.assertEqual(m.call_args_list[1][0][1], "w")
        
        handle = m()
        # Find the write() call with the resolved content
        resolved_content = ""
        for call in handle.write.call_args_list:
            resolved_content += call[0][0]
            
        self.assertEqual(resolved_content, template_content)


    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    @patch("adjutant.engine.AdjutantHUD")
    @patch("adjutant.engine.SCVOverseer")
    def test_run_adjutant_agent_hud_integration(self, mock_overseer_class, mock_hud_class, mock_remove, mock_exists, mock_run):
        mock_exists.return_value = True
        mock_hud_instance = mock_hud_class.return_value
        
        run_adjutant_agent("Test")
        
        mock_hud_class.assert_called_once_with(mission="Test")
        mock_hud_instance.start.assert_called_once()
        mock_hud_instance.stop.assert_called_once()

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    @patch("adjutant.engine.AdjutantHUD")
    @patch("adjutant.engine.SCVOverseer")
    def test_run_adjutant_agent_gemini_not_found(self, mock_overseer_class, mock_hud_class, mock_remove, mock_exists, mock_run):
        mock_exists.return_value = True
        mock_run.side_effect = FileNotFoundError()
        
        with patch("sys.exit") as mock_exit:
            with patch("builtins.print") as mock_print:
                # Mocking open to avoid file system interaction
                with patch("builtins.open", mock_open(read_data="template")):
                    run_adjutant_agent("Test")
        
        mock_exit.assert_called_with(1)
        mock_print.assert_any_call("Error: 'gemini' CLI not found. Please ensure it is installed and in your PATH.")

if __name__ == "__main__":
    unittest.main()
