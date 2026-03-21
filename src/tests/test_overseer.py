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

    @patch("adjutant.engine.SCVOverseer._get_registry_from_worktrees")
    @patch("os.path.exists")
    @patch("os.kill")
    @patch("builtins.open")
    @patch("adjutant.engine.spawn_agent")
    def test_overseer_restarts_on_quota_crash(self, mock_spawn, mock_open_file, mock_kill, mock_exists, mock_get_registry):
        # Mock registry from worktrees
        registry_data = {
            "obj-123": {
                "pid": 999,
                "agent_name": "scv-coder",
                "model": "gemini-3.1-pro-preview"
            }
        }
        mock_get_registry.return_value = registry_data
        
        # Mock log file content
        log_content = "Some logs... MODEL_CAPACITY_EXHAUSTED ... more logs"
        
        # Setup mock_open for different files
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
        
        # Verify spawn_agent called with fallback model
        mock_spawn.assert_called_with("scv-coder", "obj-123", starting_model="gemini-3-flash-preview")

    @patch("adjutant.engine.SCVOverseer._get_registry_from_worktrees")
    @patch("os.path.exists")
    @patch("os.kill")
    @patch("builtins.open")
    @patch("adjutant.engine.spawn_agent")
    def test_overseer_handles_resource_exhausted(self, mock_spawn, mock_open_file, mock_kill, mock_exists, mock_get_registry):
        # Mock registry from worktrees
        registry_data = {
            "obj-123": {
                "pid": 999,
                "agent_name": "scv-coder",
                "model": "gemini-3.1-pro-preview"
            }
        }
        mock_get_registry.return_value = registry_data
        
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

class TestSCVOverseerWorktrees(unittest.TestCase):
    def setUp(self):
        self.overseer = SCVOverseer(interval=1)
        self.project_root = self.overseer.project_root
        self.worktrees_dir = os.path.join(self.project_root, ".adjutant", "worktrees")

    @patch("os.path.exists")
    @patch("os.listdir")
    @patch("os.path.isdir")
    @patch("builtins.open", new_callable=mock_open)
    def test_get_registry_from_worktrees(self, mock_open_file, mock_isdir, mock_listdir, mock_exists):
        # Setup
        mock_exists.return_value = True
        mock_listdir.return_value = ["obj-1", "obj-2", "not-a-dir", ".hidden"]
        
        def isdir_side_effect(path):
            return "not-a-dir" not in path and ".hidden" not in path
        mock_isdir.side_effect = isdir_side_effect
        
        scv_info_1 = {"pid": 101, "agent_name": "scv-coder", "model": "m1"}
        scv_info_2 = {"pid": 102, "agent_name": "scv-tester", "model": "m2"}
        
        def open_side_effect(path, mode="r"):
            if "obj-1/.scv_info.json" in path:
                return mock_open(read_data=json.dumps(scv_info_1)).return_value
            if "obj-2/.scv_info.json" in path:
                return mock_open(read_data=json.dumps(scv_info_2)).return_value
            return mock_open().return_value
            
        mock_open_file.side_effect = open_side_effect
        
        # Execute
        registry = self.overseer._get_registry_from_worktrees()
        
        # Verify
        self.assertEqual(len(registry), 2)
        self.assertEqual(registry["obj-1"]["pid"], 101)
        self.assertEqual(registry["obj-2"]["pid"], 102)
        self.assertNotIn(".hidden", registry)
        self.assertNotIn("not-a-dir", registry)

    @patch("adjutant.engine.SCVOverseer._get_registry_from_worktrees")
    @patch("os.path.exists")
    @patch("os.kill")
    @patch("builtins.open", new_callable=mock_open)
    @patch("adjutant.engine.spawn_agent")
    @patch("adjutant.engine.cleanup_scv")
    def test_check_scvs_crashed_restart(self, mock_cleanup, mock_spawn, mock_open_file, mock_kill, mock_exists, mock_get_registry):
        # Setup registry
        registry = {
            "obj-crash": {
                "pid": 999,
                "agent_name": "scv-coder",
                "model": "gemini-3.1-pro-preview"
            }
        }
        mock_get_registry.return_value = registry
        
        # Mock crash: is_process_running(999) -> False
        mock_kill.side_effect = ProcessLookupError()
        
        # Setup mock_open for different files
        def open_side_effect(path, mode="r"):
            if "obj-crash.log" in path:
                return mock_open(read_data="RESOURCE_EXHAUSTED").return_value
            if "active_scvs.json" in path:
                if "r" in mode:
                    return mock_open(read_data=json.dumps(registry)).return_value
                else:
                    return MagicMock()
            return mock_open().return_value

        mock_open_file.side_effect = open_side_effect
        mock_exists.return_value = True # For log path and registry path
        
        # Execute
        self.overseer._check_scvs()
        
        # Verify restart
        mock_spawn.assert_called_with("scv-coder", "obj-crash", starting_model="gemini-3-flash-preview")
        mock_cleanup.assert_not_called()

    @patch("adjutant.engine.SCVOverseer._get_registry_from_worktrees")
    @patch("os.path.exists")
    @patch("os.kill")
    @patch("builtins.open", new_callable=mock_open)
    @patch("adjutant.engine.cleanup_scv")
    def test_check_scvs_crashed_cleanup(self, mock_cleanup, mock_open_file, mock_kill, mock_exists, mock_get_registry):
        # Setup registry
        registry = {
            "obj-done": {
                "pid": 888,
                "agent_name": "scv-coder",
                "model": "gemini-3.1-pro-preview"
            }
        }
        mock_get_registry.return_value = registry
        
        # Mock crash: is_process_running(888) -> False
        mock_kill.side_effect = ProcessLookupError()
        
        # Setup mock_open for different files
        def open_side_effect(path, mode="r"):
            if "obj-done.log" in path:
                return mock_open(read_data="Success!").return_value
            if "active_scvs.json" in path:
                if "r" in mode:
                    return mock_open(read_data=json.dumps(registry)).return_value
                else:
                    return MagicMock()
            return mock_open().return_value

        mock_open_file.side_effect = open_side_effect
        mock_exists.return_value = True
        
        # Execute
        self.overseer._check_scvs()
        
        # Verify cleanup
        mock_cleanup.assert_called_with("obj-done", self.overseer.project_root)

if __name__ == "__main__":
    unittest.main()
