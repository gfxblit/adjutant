import unittest
from unittest.mock import patch
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
        
        mock_exists.side_effect = lambda p: p in [worktree_path]
        
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

if __name__ == "__main__":
    unittest.main()
