import unittest
from unittest.mock import patch, mock_open
import json
import os
from adjutant.engine import monitor_scvs, cleanup_scv

class TestSCVMonitoring(unittest.TestCase):
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    @patch("os.kill")
    @patch("adjutant.engine.cleanup_scv")
    def test_monitor_scvs_detects_finished_process(self, mock_cleanup, mock_kill, mock_file, mock_exists):
        # Setup
        project_root = "/mock/project"
        registry_path = os.path.join(project_root, ".beads", "telemetry", "active_scvs.json")
        
        mock_exists.side_effect = lambda p: p == registry_path
        
        registry_data = {
            "obj-1": {"pid": 123, "agent_name": "scv-coder"},
            "obj-2": {"pid": 456, "agent_name": "scv-tester"}
        }
        mock_file.return_value.read.return_value = json.dumps(registry_data)
        
        # obj-1 is alive, obj-2 is dead
        mock_kill.side_effect = [None, OSError()]
        
        # Execute
        monitor_scvs(project_root)
        
        # Verify
        mock_cleanup.assert_called_once_with("obj-2", project_root)
        
        # Verify registry updated (obj-2 removed)
        # We need to find the write call
        write_handle = mock_file.return_value
        written_data = ""
        for call in write_handle.write.call_args_list:
            written_data += call[0][0]
        
        if written_data:
            updated_registry = json.loads(written_data)
            self.assertIn("obj-1", updated_registry)
            self.assertNotIn("obj-2", updated_registry)

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_cleanup_scv(self, mock_remove, mock_exists, mock_run):
        # Setup
        project_root = "/mock/project"
        objective_id = "test-obj"
        worktree_path = os.path.join(project_root, ".adjutant", "worktrees", objective_id)
        prompt_path = os.path.join(project_root, ".adjutant", "worktrees", f".resolved_system_{objective_id}.md")
        
        mock_exists.side_effect = lambda p: p in [worktree_path, prompt_path]
        
        # Execute
        cleanup_scv(objective_id, project_root)
        
        # Verify git push
        mock_run.assert_any_call(
            ["git", "push", "origin", f"scv/{objective_id}"],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True
        )
        
        # Verify git worktree remove
        mock_run.assert_any_call(
            ["git", "worktree", "remove", "--force", worktree_path],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True
        )
        
        # Verify prompt removal
        mock_remove.assert_called_once_with(prompt_path)

if __name__ == "__main__":
    unittest.main()
