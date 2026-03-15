import unittest
from unittest.mock import patch
import json
from adjutant.hooks import get_mission_telemetry

class TestHooks(unittest.TestCase):
    @patch("subprocess.check_output")
    def test_get_mission_telemetry_success(self, mock_check_output):
        # Mocking 'bd list' for open, in_progress, and closed statuses
        mock_check_output.side_effect = [
            # Open objectives
            json.dumps([{"id": "obj-1", "title": "Open task", "status": "open"}]).encode(),
            # In-progress objectives
            json.dumps([{"id": "obj-2", "title": "In progress task", "status": "in_progress"}]).encode(),
            # Closed objectives
            json.dumps([{"id": "obj-3", "title": "Closed task", "status": "closed", "closed_at": "2026-03-15T00:00:00Z"}]).encode()
        ]
        
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

if __name__ == "__main__":
    unittest.main()
