import unittest
from unittest.mock import patch, mock_open, MagicMock
import json
import os
from adjutant.engine import is_process_running, recover_orphaned_scvs, cleanup_scv

class TestRecovery(unittest.TestCase):
    @patch("os.kill")
    def test_is_process_running(self, mock_kill):
        # Case 1: Process exists
        mock_kill.return_value = None
        self.assertTrue(is_process_running(1234))
        mock_kill.assert_called_with(1234, 0)
        
        # Case 2: Process doesn't exist
        mock_kill.side_effect = ProcessLookupError()
        self.assertFalse(is_process_running(5678))
        
        # Case 3: Permission error (assume running)
        mock_kill.side_effect = PermissionError()
        self.assertTrue(is_process_running(9999))

    @patch("os.path.isdir")
    @patch("os.path.exists")
    @patch("os.listdir")
    @patch("adjutant.engine.is_process_running")
    @patch("adjutant.engine.cleanup_scv")
    @patch("builtins.open", new_callable=mock_open)
    def test_recover_orphaned_scvs(self, mock_open_file, mock_cleanup, mock_is_running, mock_listdir, mock_exists, mock_isdir):
        # Setup mocks
        project_root = "/tmp/project"
        worktrees_dir = os.path.join(project_root, ".adjutant", "worktrees")
        registry_path = os.path.join(project_root, ".beads", "telemetry", "active_scvs.json")
        
        def exists_side_effect(path):
            if path == worktrees_dir: return True
            if path == registry_path: return True
            return False
        mock_exists.side_effect = exists_side_effect
        mock_isdir.return_value = True
        
        # Worktrees: one active, one orphaned (dead PID), one orphaned (not in registry)
        mock_listdir.return_value = ["active-scv", "dead-scv", "unknown-scv"]
        
        registry_data = {
            "active-scv": {"pid": 111},
            "dead-scv": {"pid": 222}
        }
        mock_open_file.return_value.__enter__.return_value.read.return_value = json.dumps(registry_data)
        
        def is_running_side_effect(pid):
            if pid == 111: return True
            if pid == 222: return False
            return False
        mock_is_running.side_effect = is_running_side_effect
        
        # Run recovery
        recover_orphaned_scvs(project_root)
        
        # Check cleanups
        self.assertEqual(mock_cleanup.call_count, 2)
        mock_cleanup.assert_any_call("dead-scv", project_root)
        mock_cleanup.assert_any_call("unknown-scv", project_root)
        
        # Check registry update
        # It should have called open(registry_path, "w")
        write_call = [call for call in mock_open_file.call_args_list if call[0][1] == "w"]
        self.assertTrue(len(write_call) > 0)
        
        # Verify content written (only active-scv should remain)
        handle = mock_open_file()
        written_data = ""
        for call in handle.write.call_args_list:
            written_data += call[0][0]
        
        updated_registry = json.loads(written_data)
        self.assertIn("active-scv", updated_registry)
        self.assertNotIn("dead-scv", updated_registry)
        self.assertNotIn("unknown-scv", updated_registry)

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_cleanup_scv(self, mock_remove, mock_exists, mock_run):
        project_root = "/tmp/project"
        objective_id = "test-obj"
        worktree_path = os.path.join(project_root, ".adjutant", "worktrees", objective_id)
        resolved_path = os.path.join(project_root, ".adjutant", "worktrees", f".resolved_system_{objective_id}.md")
        
        def exists_side_effect(path):
            if path == worktree_path: return True
            if path == resolved_path: return True
            return False
        mock_exists.side_effect = exists_side_effect
        
        cleanup_scv(objective_id, project_root)
        
        # 1. Auto-commit calls
        mock_run.assert_any_call(["git", "add", "."], cwd=worktree_path, check=False, capture_output=True)
        mock_run.assert_any_call(["git", "commit", "-m", f"Auto-commit stranded work for {objective_id}"], cwd=worktree_path, check=False, capture_output=True)
        
        # 2. Push call
        mock_run.assert_any_call(["git", "push", "origin", f"scv/{objective_id}"], cwd=project_root, check=False, capture_output=True, text=True)
        
        # 3. Worktree remove call
        mock_run.assert_any_call(["bd", "worktree", "remove", worktree_path], cwd=project_root, check=False, capture_output=True, text=True)
        
        # 4. Resolved prompt cleanup
        mock_remove.assert_called_with(resolved_path)

if __name__ == "__main__":
    unittest.main()
