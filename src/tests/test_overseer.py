import os
import json
import unittest
from unittest.mock import patch, mock_open, MagicMock
from adjutant.engine import SCVOverseer

class TestSCVOverseer(unittest.TestCase):
    def setUp(self):
        self.overseer = SCVOverseer(interval=1)
        self.registry_path = self.overseer.registry_path
        self.telemetry_dir = self.overseer.telemetry_dir

    @patch("os.path.exists")
    @patch("os.kill")
    @patch("builtins.open")
    @patch("adjutant.engine.spawn_agent")
    def test_overseer_restarts_on_quota_crash(self, mock_spawn, mock_open_file, mock_kill, mock_exists):
        # Mock registry file
        registry_data = {
            "obj-123": {
                "pid": 999,
                "agent_name": "scv-coder",
                "model": "gemini-3.1-pro-preview"
            }
        }
        
        # Mock log file content
        log_content = "Some logs... MODEL_CAPACITY_EXHAUSTED ... more logs"
        
        # Setup mock_open for different files
        def side_effect(path, mode="r"):
            if "active_scvs.json" in path:
                # For reading registry
                if "r" in mode:
                    m = mock_open(read_data=json.dumps(registry_data)).return_value
                    return m
                # For writing registry
                else:
                    return MagicMock()
            if "obj-123.log" in path:
                m = mock_open(read_data=log_content).return_value
                return m
            return mock_open().return_value

        mock_open_file.side_effect = side_effect
        mock_exists.side_effect = lambda p: True
        mock_kill.side_effect = ProcessLookupError() # Process is dead

        self.overseer._check_scvs()
        
        # Verify spawn_agent called with fallback model
        # Note: If it's not yet implemented, this might fail or call with flash-preview by default
        mock_spawn.assert_called_with("scv-coder", "obj-123", starting_model="gemini-3-flash-preview")

    @patch("os.path.exists")
    @patch("os.kill")
    @patch("builtins.open")
    @patch("adjutant.engine.spawn_agent")
    def test_overseer_handles_resource_exhausted(self, mock_spawn, mock_open_file, mock_kill, mock_exists):
        # Mock registry file
        registry_data = {
            "obj-123": {
                "pid": 999,
                "agent_name": "scv-coder",
                "model": "gemini-3.1-pro-preview"
            }
        }
        
        # Mock log file content
        log_content = "Error: RESOURCE_EXHAUSTED"
        
        def side_effect(path, mode="r"):
            if "active_scvs.json" in path:
                if "r" in mode:
                    return mock_open(read_data=json.dumps(registry_data)).return_value
                else:
                    return MagicMock()
            if "obj-123.log" in path:
                return mock_open(read_data=log_content).return_value
            return mock_open().return_value

        mock_open_file.side_effect = side_effect
        mock_exists.side_effect = lambda p: True
        mock_kill.side_effect = ProcessLookupError() # Process is dead

        self.overseer._check_scvs()
        
        # Verify spawn_agent called
        mock_spawn.assert_called_with("scv-coder", "obj-123", starting_model="gemini-3-flash-preview")

if __name__ == "__main__":
    unittest.main()
