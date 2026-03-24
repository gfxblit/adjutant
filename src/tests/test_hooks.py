import unittest
from unittest.mock import patch
import json
import io
import os
from adjutant.hooks import get_mission_telemetry, main

class TestHooks(unittest.TestCase):
    def setUp(self):
        # Ensure ADJUTANT_DISABLE_HOOK is not set during tests by default
        self.env_patcher = patch.dict(os.environ, {"ADJUTANT_DISABLE_HOOK": "0"})
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    @patch("subprocess.check_output")
    def test_get_mission_telemetry_success(self, mock_check_output):
        # Mocking 'bd list --all --json' call
        all_issues = [
            {"id": "obj-1", "title": "Open task", "status": "open"},
            {"id": "obj-2", "title": "In progress task", "status": "in_progress"},
            {"id": "obj-3", "title": "Closed task", "status": "closed", "closed_at": "2026-03-15T00:00:00Z"}
        ]
        
        def side_effect(args, **kwargs):
            if args[0] == "bd" and args[1] == "list":
                return json.dumps(all_issues).encode()
            return b"[]"
            
        mock_check_output.side_effect = side_effect
        
        telemetry = get_mission_telemetry()
        
        self.assertIn("## Mission Telemetry", telemetry)
        self.assertIn("### Active Objectives", telemetry)
        self.assertIn("- obj-1: Open task", telemetry)
        self.assertIn("- obj-2: In progress task [in_progress]", telemetry)
        self.assertIn("### Recent Activity", telemetry)
        self.assertIn("- COMPLETED: obj-3: Closed task", telemetry)

    @patch("subprocess.check_output")
    def test_get_mission_telemetry_with_pr_status(self, mock_check_output):
        # Mocking 'bd list --all --json' call
        all_issues = [
            {"id": "obj-1", "title": "Open task", "status": "open"}
        ]
        # Mocking 'bd show --json obj-1' call
        show_details = [
            {
                "id": "obj-1",
                "comments": [
                    {"text": "Fixed in https://github.com/owner/repo/pull/123"}
                ]
            }
        ]
        # Mocking 'gh pr list' call
        gh_prs = [
            {"url": "https://github.com/owner/repo/pull/123", "state": "OPEN", "number": 123}
        ]

        def side_effect(args, **kwargs):
            if args[0] == "bd" and args[1] == "list":
                return json.dumps(all_issues).encode()
            if args[0] == "bd" and args[1] == "show":
                return json.dumps(show_details).encode()
            if args[0] == "gh" and args[1] == "pr" and args[2] == "list":
                return json.dumps(gh_prs).encode()
            return b"[]"

        mock_check_output.side_effect = side_effect
        
        telemetry = get_mission_telemetry()
        
        self.assertIn("- obj-1: Open task [PR #123 OPEN]", telemetry)

    @patch("subprocess.check_output")
    def test_get_mission_telemetry_multiple_prs(self, mock_check_output):
        all_issues = [
            {"id": "obj-1", "title": "Task 1", "status": "in_progress"}
        ]
        show_details = [
            {
                "id": "obj-1",
                "comments": [
                    {"text": "Work in https://github.com/owner/repo/pull/123"},
                    {"text": "Also in https://github.com/owner/repo/pull/124"}
                ]
            }
        ]
        gh_prs = [
            {"url": "https://github.com/owner/repo/pull/123", "state": "MERGED", "number": 123},
            {"url": "https://github.com/owner/repo/pull/124", "state": "OPEN", "number": 124}
        ]

        def side_effect(args, **kwargs):
            if args[0] == "bd" and args[1] == "list":
                return json.dumps(all_issues).encode()
            if args[0] == "bd" and args[1] == "show":
                return json.dumps(show_details).encode()
            if args[0] == "gh" and args[1] == "pr" and args[2] == "list":
                return json.dumps(gh_prs).encode()
            return b"[]"

        mock_check_output.side_effect = side_effect
        
        telemetry = get_mission_telemetry()
        
        self.assertIn("- obj-1: Task 1 [in_progress] [PR #123 MERGED, PR #124 OPEN]", telemetry)

    @patch("subprocess.check_output")
    def test_get_mission_telemetry_gh_failure(self, mock_check_output):
        all_issues = [
            {"id": "obj-1", "title": "Open task", "status": "open"}
        ]
        show_details = [
            {
                "id": "obj-1",
                "comments": [{"text": "https://github.com/owner/repo/pull/123"}]
            }
        ]

        def side_effect(args, **kwargs):
            if args[0] == "bd" and args[1] == "list":
                return json.dumps(all_issues).encode()
            if args[0] == "bd" and args[1] == "show":
                return json.dumps(show_details).encode()
            if args[0] == "gh":
                raise Exception("gh failed")
            return b"[]"

        mock_check_output.side_effect = side_effect
        
        # Should not crash, just not include PR info
        telemetry = get_mission_telemetry()
        self.assertIn("- obj-1: Open task", telemetry)
        self.assertNotIn("PR #123", telemetry)

    @patch("subprocess.check_output")
    def test_get_mission_telemetry_no_pr_links(self, mock_check_output):
        all_issues = [{"id": "obj-1", "title": "Open task", "status": "open"}]
        show_details = [{"id": "obj-1", "comments": [{"text": "No links here"}]}]

        def side_effect(args, **kwargs):
            if args[0] == "bd" and args[1] == "list":
                return json.dumps(all_issues).encode()
            if args[0] == "bd" and args[1] == "show":
                return json.dumps(show_details).encode()
            return b"[]"

        mock_check_output.side_effect = side_effect
        
        telemetry = get_mission_telemetry()
        self.assertIn("- obj-1: Open task", telemetry)
        self.assertNotIn("[PR #", telemetry)

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

    @patch("sys.stdout", new_callable=io.StringIO)
    def test_cli_hook_protocol_disabled(self, mock_stdout):
        # Mocking environment variable disable hook
        with patch.dict(os.environ, {"ADJUTANT_DISABLE_HOOK": "1"}):
            # Call the CLI entry point
            main()
            
            # Verify output JSON is empty
            output_data = json.loads(mock_stdout.getvalue())
            self.assertEqual(output_data, {"hookSpecificOutput": {}})

if __name__ == "__main__":
    unittest.main()
