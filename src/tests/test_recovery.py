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
    def test_recover_orphaned_scvs(self, mock_cleanup, mock_is_running, mock_listdir, mock_exists, mock_isdir):
        # Setup mocks
        project_root = "/tmp/project"
        worktrees_dir = os.path.join(project_root, ".adjutant", "worktrees")
        
        # Define SCV info paths
        active_scv_info = os.path.join(worktrees_dir, "active-scv", ".scv_info.json")
        dead_scv_info = os.path.join(worktrees_dir, "dead-scv", ".scv_info.json")
        
        def exists_side_effect(path):
            if path == worktrees_dir: return True
            if path == active_scv_info: return True
            if path == dead_scv_info: return True
            return False
        mock_exists.side_effect = exists_side_effect
        mock_isdir.return_value = True
        
        # Worktrees: one active, one orphaned (dead PID), one orphaned (no .scv_info.json)
        mock_listdir.return_value = ["active-scv", "dead-scv", "unknown-scv"]
        
        def is_running_side_effect(pid):
            if pid == 111: return True
            if pid == 222: return False
            return False
        mock_is_running.side_effect = is_running_side_effect

        # Mock open for multiple files
        file_contents = {
            active_scv_info: json.dumps({"pid": 111}),
            dead_scv_info: json.dumps({"pid": 222}),
        }

        class MockFile:
            def __init__(self, path, mode):
                self.path = path
                self.mode = mode
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return file_contents.get(self.path, "")
            def write(self, data):
                pass

        with patch("builtins.open", side_effect=MockFile):
            # Run recovery
            recover_orphaned_scvs(project_root)
        
        # Check cleanups: dead-scv (PID dead) and unknown-scv (no info file)
        self.assertEqual(mock_cleanup.call_count, 2)
        mock_cleanup.assert_any_call("dead-scv", project_root)
        mock_cleanup.assert_any_call("unknown-scv", project_root)

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
        
        # Mock subprocess.run to return success by default
        mock_run.return_value = MagicMock(returncode=0)

        cleanup_scv(objective_id, project_root)
        
        # 1. Auto-commit calls
        mock_run.assert_any_call(["git", "add", "."], cwd=worktree_path, check=False, capture_output=True)
        mock_run.assert_any_call(["git", "commit", "-m", f"Auto-commit stranded work for {objective_id}"], cwd=worktree_path, check=False, capture_output=True)
        
        # 2. Push call
        mock_run.assert_any_call(["git", "push", "origin", f"scv/{objective_id}"], cwd=project_root, check=False, capture_output=True, text=True)
        
        # 3. Worktree remove call (always uses --force)
        mock_run.assert_any_call(["bd", "worktree", "remove", "--force", worktree_path], cwd=project_root, check=False, capture_output=True, text=True)
        
        # 4. Resolved prompt cleanup
        mock_remove.assert_called_with(resolved_path)

    @patch("adjutant.engine.logger")
    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_cleanup_scv_push_failure(self, mock_remove, mock_exists, mock_run, mock_logger):
        project_root = "/tmp/project"
        objective_id = "test-obj"
        worktree_path = os.path.join(project_root, ".adjutant", "worktrees", objective_id)
        resolved_path = os.path.join(project_root, ".adjutant", "worktrees", f".resolved_system_{objective_id}.md")
        
        def exists_side_effect(path):
            return True # Assume everything exists
        mock_exists.side_effect = exists_side_effect
        
        # Mock subprocess.run to raise exception for push command
        def run_side_effect(cmd, **kwargs):
            if "push" in cmd:
                raise Exception("Push failed")
            return MagicMock(returncode=0)
            
        mock_run.side_effect = run_side_effect
        
        # This should not raise an exception, but log the error
        cleanup_scv(objective_id, project_root)
        
        # Verify that other steps were still attempted
        mock_run.assert_any_call(["git", "add", "."], cwd=worktree_path, check=False, capture_output=True)
        mock_run.assert_any_call(["bd", "worktree", "remove", "--force", worktree_path], cwd=project_root, check=False, capture_output=True, text=True)
        mock_remove.assert_called_with(resolved_path)
        
        # Verify logger was called for the failure
        mock_logger.info.assert_any_call("Failed to push branch scv/test-obj: Push failed")

    @patch("adjutant.engine.logger")
    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_cleanup_scv_commit_failure(self, mock_remove, mock_exists, mock_run, mock_logger):
        project_root = "/tmp/project"
        objective_id = "test-obj"
        worktree_path = os.path.join(project_root, ".adjutant", "worktrees", objective_id)
        resolved_path = os.path.join(project_root, ".adjutant", "worktrees", f".resolved_system_{objective_id}.md")
        
        def exists_side_effect(path):
            return True # Assume everything exists
        mock_exists.side_effect = exists_side_effect
        
        # Mock subprocess.run to raise exception for commit command
        def run_side_effect(cmd, **kwargs):
            if "commit" in cmd:
                raise Exception("Commit failed")
            return MagicMock(returncode=0)
            
        mock_run.side_effect = run_side_effect
        
        # This should not raise an exception, but log the error
        cleanup_scv(objective_id, project_root)
        
        # Verify that steps were attempted despite commit failure (best-effort)
        mock_run.assert_any_call(["git", "add", "."], cwd=worktree_path, check=False, capture_output=True)
        mock_run.assert_any_call(["git", "commit", "-m", f"Auto-commit stranded work for {objective_id}"], cwd=worktree_path, check=False, capture_output=True)
        
        # In current implementation, it continues to push and remove
        mock_run.assert_any_call(["git", "push", "origin", f"scv/{objective_id}"], cwd=project_root, check=False, capture_output=True, text=True)
        mock_run.assert_any_call(["bd", "worktree", "remove", "--force", worktree_path], cwd=project_root, check=False, capture_output=True, text=True)
        mock_remove.assert_called_with(resolved_path)
        
        # Verify logger was called for the failure
        mock_logger.info.assert_any_call("Failed to auto-commit worktree test-obj: Commit failed")

    @patch("adjutant.engine.logger")
    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_cleanup_scv_remove_failure(self, mock_remove, mock_exists, mock_run, mock_logger):
        project_root = "/tmp/project"
        objective_id = "test-obj"
        worktree_path = os.path.join(project_root, ".adjutant", "worktrees", objective_id)
        resolved_path = os.path.join(project_root, ".adjutant", "worktrees", f".resolved_system_{objective_id}.md")
        
        def exists_side_effect(path):
            return True # Assume everything exists
        mock_exists.side_effect = exists_side_effect
        
        # Mock subprocess.run to raise exception for 'bd worktree remove' command
        def run_side_effect(cmd, **kwargs):
            if "bd" in cmd and "worktree" in cmd and "remove" in cmd:
                raise Exception("Worktree removal failed")
            return MagicMock(returncode=0)
            
        mock_run.side_effect = run_side_effect
        
        # This should not raise an exception, but log the error
        cleanup_scv(objective_id, project_root)
        
        # Verify that steps before removal were attempted
        mock_run.assert_any_call(["git", "add", "."], cwd=worktree_path, check=False, capture_output=True)
        mock_run.assert_any_call(["git", "commit", "-m", f"Auto-commit stranded work for {objective_id}"], cwd=worktree_path, check=False, capture_output=True)
        mock_run.assert_any_call(["git", "push", "origin", f"scv/{objective_id}"], cwd=project_root, check=False, capture_output=True, text=True)
        # Worktree remove should be called, but it will fail
        mock_run.assert_any_call(["bd", "worktree", "remove", "--force", worktree_path], cwd=project_root, check=False, capture_output=True, text=True)
        # Resolved path removal should STILL be attempted if worktree removal fails (best-effort)
        mock_remove.assert_called_with(resolved_path)
        
        # Verify logger was called for the failure
        mock_logger.info.assert_any_call("Failed to remove worktree test-obj: Worktree removal failed")

    @patch("adjutant.engine.logger")
    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_cleanup_scv_resolved_path_remove_failure(self, mock_remove, mock_exists, mock_run, mock_logger):
        project_root = "/tmp/project"
        objective_id = "test-obj"
        worktree_path = os.path.join(project_root, ".adjutant", "worktrees", objective_id)
        resolved_path = os.path.join(project_root, ".adjutant", "worktrees", f".resolved_system_{objective_id}.md")
        
        def exists_side_effect(path):
            if path == worktree_path: return True
            if path == resolved_path: return True
            return False
        mock_exists.side_effect = exists_side_effect
        
        # Mock subprocess.run to succeed, but os.remove to fail
        mock_run.return_value = MagicMock(returncode=0)
        mock_remove.side_effect = Exception("Failed to remove resolved path")
        
        # This should not raise an exception, but log the error
        cleanup_scv(objective_id, project_root)
        
        # Verify that all steps before os.remove were attempted
        mock_run.assert_any_call(["git", "add", "."], cwd=worktree_path, check=False, capture_output=True)
        mock_run.assert_any_call(["git", "commit", "-m", f"Auto-commit stranded work for {objective_id}"], cwd=worktree_path, check=False, capture_output=True)
        mock_run.assert_any_call(["git", "push", "origin", f"scv/{objective_id}"], cwd=project_root, check=False, capture_output=True, text=True)
        mock_run.assert_any_call(["bd", "worktree", "remove", "--force", worktree_path], cwd=project_root, check=False, capture_output=True, text=True)
        # Resolved path remove should be called, but it will fail
        mock_remove.assert_called_with(resolved_path)
        
        # Verify logger was called for the failure
        mock_logger.info.assert_any_call("Failed to remove resolved prompt file test-obj: Failed to remove resolved path")

if __name__ == "__main__":
    unittest.main()
