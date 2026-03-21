import unittest
from unittest.mock import patch, MagicMock
import os
from adjutant.engine import cleanup_scv

class TestSCVMonitoring(unittest.TestCase):
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
        
        # Mock git status showing NO changes
        def mock_run_side_effect(cmd, **kwargs):
            return MagicMock(stdout="", returncode=0)
        mock_run.side_effect = mock_run_side_effect
        
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
        
        # Verify bd worktree remove
        mock_run.assert_any_call(
            ["bd", "worktree", "remove", worktree_path],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True
        )
        
        # Verify prompt removal
        mock_remove.assert_called_once_with(prompt_path)

    @patch("subprocess.run")
    @patch("os.path.exists")
    @patch("os.remove")
    def test_cleanup_scv_with_changes(self, mock_remove, mock_exists, mock_run):
        # Setup
        project_root = "/mock/project"
        objective_id = "test-obj"
        worktree_path = os.path.join(project_root, ".adjutant", "worktrees", objective_id)
        
        mock_exists.side_effect = lambda p: p == worktree_path
        
        # Mock git status showing changes
        def mock_run_side_effect(cmd, **kwargs):
            if cmd == ["git", "status", "--porcelain"]:
                return MagicMock(stdout="M file.txt\n", returncode=0)
            return MagicMock(stdout="", returncode=0)
            
        mock_run.side_effect = mock_run_side_effect
        
        # Execute
        cleanup_scv(objective_id, project_root)
        
        # Verify auto-commit
        mock_run.assert_any_call(["git", "add", "-A"], cwd=worktree_path, check=True)
        mock_run.assert_any_call(
            ["git", "commit", "-m", "[SCV Auto-Commit] Work in progress before cleanup"],
            cwd=worktree_path,
            check=True
        )
        
        # Verify git push still happens
        mock_run.assert_any_call(
            ["git", "push", "origin", f"scv/{objective_id}"],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True
        )

if __name__ == "__main__":
    unittest.main()
