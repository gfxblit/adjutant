import pytest
from unittest.mock import patch, MagicMock
import os
import json
from adjutant.engine import SCVOverseer

@pytest.fixture
def overseer():
    return SCVOverseer(interval=1)

@pytest.fixture
def mock_overseer_deps():
    with patch("os.path.exists") as m_exists, \
         patch("os.kill") as m_kill, \
         patch("builtins.open") as m_open, \
         patch("adjutant.engine.spawn_agent") as m_spawn, \
         patch("adjutant.engine.cleanup_scv") as m_cleanup:
        yield {
            "exists": m_exists,
            "kill": m_kill,
            "open": m_open,
            "spawn": m_spawn,
            "cleanup": m_cleanup
        }

def test_overseer_restarts_on_quota_crash(overseer, mock_overseer_deps):
    # Mock registry from worktrees
    registry_data = {
        "obj-123": {
            "pid": 999,
            "agent_name": "scv-coder",
            "model": "gemini-3.1-pro-preview"
        }
    }
    with patch.object(overseer, "_get_registry_from_worktrees", return_value=registry_data):
        # Mock log file content
        log_content = "Some logs... MODEL_CAPACITY_EXHAUSTED ... more logs"
        
        def side_effect(path, mode="r"):
            if "obj-123.log" in path:
                m = MagicMock()
                m.__enter__.return_value = m
                m.read.return_value = log_content
                return m
            return MagicMock()

        mock_overseer_deps["open"].side_effect = side_effect
        mock_overseer_deps["exists"].return_value = True
        mock_overseer_deps["kill"].side_effect = ProcessLookupError() # Process is dead

        overseer._check_scvs()
        
        # Verify spawn_agent called with fallback model
        mock_overseer_deps["spawn"].assert_called_with("scv-coder", "obj-123", starting_model="gemini-3-flash-preview")

def test_overseer_handles_resource_exhausted(overseer, mock_overseer_deps):
    # Mock registry from worktrees
    registry_data = {
        "obj-123": {
            "pid": 999,
            "agent_name": "scv-coder",
            "model": "gemini-3.1-pro-preview"
        }
    }
    with patch.object(overseer, "_get_registry_from_worktrees", return_value=registry_data):
        log_content = "Error: RESOURCE_EXHAUSTED"
        
        def side_effect(path, mode="r"):
            if "obj-123.log" in path:
                m = MagicMock()
                m.__enter__.return_value = m
                m.read.return_value = log_content
                return m
            return MagicMock()

        mock_overseer_deps["open"].side_effect = side_effect
        mock_overseer_deps["exists"].return_value = True
        mock_overseer_deps["kill"].side_effect = ProcessLookupError() # Process is dead

        overseer._check_scvs()
        
        mock_overseer_deps["spawn"].assert_called_with("scv-coder", "obj-123", starting_model="gemini-3-flash-preview")

def test_get_registry_from_worktrees(overseer):
    with patch("os.path.exists", return_value=True), \
         patch("os.listdir", return_value=["obj-1", "obj-2", "not-a-dir", ".hidden"]), \
         patch("os.path.isdir") as mock_isdir, \
         patch("builtins.open") as mock_open_file:
        
        def isdir_side_effect(path):
            return "not-a-dir" not in path and ".hidden" not in path
        mock_isdir.side_effect = isdir_side_effect
        
        scv_info_1 = {"pid": 101, "agent_name": "scv-coder", "model": "m1"}
        scv_info_2 = {"pid": 102, "agent_name": "scv-tester", "model": "m2"}
        
        def open_side_effect(path, mode="r"):
            m = MagicMock()
            m.__enter__.return_value = m
            if "obj-1/.scv_info.json" in path:
                m.read.return_value = json.dumps(scv_info_1)
            elif "obj-2/.scv_info.json" in path:
                m.read.return_value = json.dumps(scv_info_2)
            return m
            
        mock_open_file.side_effect = open_side_effect
        
        registry = overseer._get_registry_from_worktrees()
        
        assert len(registry) == 2
        assert registry["obj-1"]["pid"] == 101
        assert registry["obj-2"]["pid"] == 102
        assert ".hidden" not in registry
        assert "not-a-dir" not in registry

def test_check_scvs_crashed_restart(overseer, mock_overseer_deps):
    registry = {
        "obj-crash": {
            "pid": 999,
            "agent_name": "scv-coder",
            "model": "gemini-3.1-pro-preview"
        }
    }
    with patch.object(overseer, "_get_registry_from_worktrees", return_value=registry):
        mock_overseer_deps["kill"].side_effect = ProcessLookupError()
        
        def open_side_effect(path, mode="r"):
            m = MagicMock()
            m.__enter__.return_value = m
            if "obj-crash.log" in path:
                m.read.return_value = "RESOURCE_EXHAUSTED"
            return m

        mock_overseer_deps["open"].side_effect = open_side_effect
        mock_overseer_deps["exists"].return_value = True
        
        overseer._check_scvs()
        
        mock_overseer_deps["spawn"].assert_called_with("scv-coder", "obj-crash", starting_model="gemini-3-flash-preview")
        mock_overseer_deps["cleanup"].assert_not_called()

def test_check_scvs_crashed_cleanup(overseer, mock_overseer_deps):
    registry = {
        "obj-done": {
            "pid": 888,
            "agent_name": "scv-coder",
            "model": "gemini-3.1-pro-preview"
        }
    }
    with patch.object(overseer, "_get_registry_from_worktrees", return_value=registry):
        mock_overseer_deps["kill"].side_effect = ProcessLookupError()
        
        def open_side_effect(path, mode="r"):
            m = MagicMock()
            m.__enter__.return_value = m
            if "obj-done.log" in path:
                m.read.return_value = "Success!"
            return m

        mock_overseer_deps["open"].side_effect = open_side_effect
        mock_overseer_deps["exists"].return_value = True
        
        overseer._check_scvs()
        
        mock_overseer_deps["cleanup"].assert_called_with("obj-done", overseer.project_root)

def test_check_scvs_exhausted_cleanup(overseer, mock_overseer_deps):
    registry = {
        "obj-exhausted": {
            "pid": 777,
            "agent_name": "scv-coder",
            "model": overseer.MODELS[-1]
        }
    }
    with patch.object(overseer, "_get_registry_from_worktrees", return_value=registry):
        mock_overseer_deps["kill"].side_effect = ProcessLookupError()
        
        def open_side_effect(path, mode="r"):
            m = MagicMock()
            m.__enter__.return_value = m
            if "obj-exhausted.log" in path:
                m.read.return_value = "RESOURCE_EXHAUSTED"
            return m

        mock_overseer_deps["open"].side_effect = open_side_effect
        mock_overseer_deps["exists"].return_value = True
        
        overseer._check_scvs()
        
        mock_overseer_deps["cleanup"].assert_called_with("obj-exhausted", overseer.project_root)
