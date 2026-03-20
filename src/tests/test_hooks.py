import unittest
from unittest.mock import patch, MagicMock
import json
import io
import sys
from adjutant.hooks import get_mission_telemetry, main

class TestHooks(unittest.TestCase):
    @patch("subprocess.check_output")
    def test_get_mission_telemetry_success(self, mock_check_output):
        # Mocking 'bd list --all --json' call
        all_issues = [
            {"id": "obj-1", "title": "Open task", "status": "open"},
            {"id": "obj-2", "title": "In progress task", "status": "in_progress"},
            {"id": "obj-3", "title": "Closed task", "status": "closed", "closed_at": "2026-03-15T00:00:00Z"}
        ]
        mock_check_output.return_value = json.dumps(all_issues).encode()
        
        telemetry = get_mission_telemetry()
        
        self.assertIn("## Mission Telemetry", telemetry)
        self.assertIn("### Active Objectives", telemetry)
        self.assertIn("- obj-1: Open task", telemetry)
        self.assertIn("- obj-2: In progress task [in_progress]", telemetry)
        self.assertIn("### Recent Activity", telemetry)
        self.assertIn("- COMPLETED: obj-3: Closed task", telemetry)

    @patch("subprocess.check_output")
    def test_get_mission_telemetry_handles_error(self, mock_check_output):
        mock_check_output.side_effect = Exception("error")
        
        telemetry = get_mission_telemetry()
        self.assertEqual(telemetry, "Mission telemetry unavailable")

    @patch("adjutant.hooks.get_mission_telemetry")
    @patch("sys.stdin", new_callable=io.StringIO)
    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_hook_protocol(self, mock_stdout, mock_stdin, mock_get_telemetry):
        # Mocking input JSON from Gemini
        input_data = {
            "hookName": "BeforeAgent",
            "agent": {"name": "TestAgent"},
            "mission": {"id": "test-mission"}
        }
        mock_stdin.write(json.dumps(input_data))
        mock_stdin.seek(0)
        
        # Mocking telemetry result
        mock_get_telemetry.return_value = "Mocked Telemetry"
        
        # Call the CLI entry point
        main()
        
        # Verify output JSON
        output_data = json.loads(mock_stdout.getvalue())
        expected_output = {
            "hookSpecificOutput": {
                "additionalContext": "Mocked Telemetry"
            }
        }
        self.assertEqual(output_data, expected_output)

if __name__ == "__main__":
    unittest.main()
