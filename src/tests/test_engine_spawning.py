from unittest.mock import patch, mock_open, MagicMock
from adjutant.engine import spawn_agent, get_project_root
import pytest
import os
import json

@patch("adjutant.engine.get_project_root")
@patch("subprocess.run")
@patch("subprocess.Popen")
@patch("os.makedirs")
@patch("os.path.exists")
def test_spawn_agent_scv_coder(mock_exists, mock_makedirs, mock_popen, mock_run, mock_get_root):
    # Setup
    agent_name = "scv-coder"
    objective_id = "test-obj-123"
    project_root = "/mock/project"
    mock_get_root.return_value = project_root
    mock_exists.return_value = True
    mock_popen.return_value.pid = 12345
    
    # Mock multiple open calls
    # 1. Reading system.md
    # 2. Writing resolved system prompt
    # 3. Appending to log file
    # 4. Reading registry (if exists)
    # 5. Writing registry
    system_prompt_content = "Coder Prompt for {objective_id}"
    m = mock_open(read_data=system_prompt_content)
    
    with patch("builtins.open", m):
        # Execute
        spawn_agent(agent_name, objective_id)
    
    # Verify bd update call
    mock_run.assert_any_call(
        ["bd", "update", objective_id, "--status", "in_progress"],
        check=False,
        stderr=-3 # subprocess.DEVNULL
    )
    
    # Verify bd worktree create call
    worktree_path = os.path.join(project_root, ".adjutant", "worktrees", objective_id)
    mock_run.assert_any_call(
        ["bd", "worktree", "create", worktree_path, "--branch", f"scv/{objective_id}"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True
    )
    
    # Verify subprocess call
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    
    # Extract command from args
    cmd = args[0]
    assert cmd[0] == "gemini"
    assert "--model" in cmd
    assert "gemini-3.1-pro-preview" in cmd
    assert "--include-directories" in cmd
    assert "-p" in cmd
    assert "Execute mission." in cmd

    # Verify cwd is set to worktree
    assert kwargs.get("cwd", "").endswith(f"worktrees/{objective_id}")

    # Verify log file was closed in parent
    mock_file = m.return_value
    mock_file.close.assert_called()

    # Verify .scv_info.json was written
    expected_scv_info_path = os.path.join(worktree_path, ".scv_info.json")
    
    # Check if any call to open was for .scv_info.json
    found_scv_info_open = False
    for call in m.call_args_list:
        if call[0][0] == expected_scv_info_path:
            found_scv_info_open = True
            assert call[0][1] == "w"
            break
    assert found_scv_info_open, f"Did not find open call for {expected_scv_info_path}"

    # Verify content of .scv_info.json
    handle = m()
    # Collect all writes
    all_writes = [call[0][0] for call in handle.write.call_args_list]
    full_content = "".join(all_writes)
    
    assert '"pid": 12345' in full_content
    assert f'"agent_name": "{agent_name}"' in full_content
    assert '"model": "gemini-3.1-pro-preview"' in full_content

@patch("adjutant.engine.get_project_root")
@patch("subprocess.run")
@patch("subprocess.Popen")
@patch("os.makedirs")
@patch("os.path.exists")
def test_spawn_agent_scv_tester(mock_exists, mock_makedirs, mock_popen, mock_run, mock_get_root):
    # Setup
    agent_name = "scv-tester"
    objective_id = "test-obj-456"
    project_root = "/mock/project"
    mock_get_root.return_value = project_root
    mock_exists.return_value = True
    mock_popen.return_value.pid = 67890
    
    system_prompt_content = "Tester Prompt for {objective_id}"
    m = mock_open(read_data=system_prompt_content)
    
    with patch("builtins.open", m):
        # Execute
        spawn_agent(agent_name, objective_id)
    
    # Verify subprocess call
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    
    # Extract command from args
    cmd = args[0]
    assert cmd[0] == "gemini"

def test_spawn_agent_invalid_name():
    with pytest.raises(ValueError, match="Unknown agent or missing system prompt: invalid-agent"):
        spawn_agent("invalid-agent", "some-id")
