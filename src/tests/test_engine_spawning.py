from unittest.mock import patch, mock_open, MagicMock
from adjutant.engine import spawn_agent
import pytest
import os
import json

@patch("subprocess.run")
@patch("subprocess.Popen")
@patch("os.makedirs")
@patch("os.path.exists")
def test_spawn_agent_scv_coder(mock_exists, mock_makedirs, mock_popen, mock_run):
    # Setup
    agent_name = "scv-coder"
    objective_id = "test-obj-123"
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
    mock_run.assert_any_call(
        ["bd", "worktree", "create", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".adjutant", "worktrees", objective_id), "--branch", f"scv/{objective_id}"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
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

@patch("subprocess.run")
@patch("subprocess.Popen")
@patch("os.makedirs")
@patch("os.path.exists")
def test_spawn_agent_scv_tester(mock_exists, mock_makedirs, mock_popen, mock_run):
    # Setup
    agent_name = "scv-tester"
    objective_id = "test-obj-456"
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
