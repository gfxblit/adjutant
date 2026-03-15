import os
import subprocess
from unittest.mock import patch, MagicMock
from adjutant.engine import spawn_agent
import pytest

@patch("subprocess.Popen")
@patch("os.makedirs")
@patch("builtins.open", new_callable=MagicMock)
def test_spawn_agent_scv_coder(mock_open, mock_makedirs, mock_popen):
    # Setup
    agent_name = "scv-coder"
    objective_id = "test-obj-123"
    
    # Mock file handle for telemetry
    mock_file = MagicMock()
    mock_open.return_value = mock_file
    
    # Execute
    spawn_agent(agent_name, objective_id)
    
    # Verify telemetry directory creation
    # We check if it ends with .beads/telemetry since absolute path varies
    assert mock_makedirs.call_args[0][0].endswith(".beads/telemetry")
    assert mock_makedirs.call_args[1]["exist_ok"] is True
    
    # Verify telemetry log file opening
    # We check if it ends with test-obj-123.log
    assert mock_open.call_args[0][0].endswith(f"{objective_id}.log")
    assert mock_open.call_args[0][1] == "w"
    
    # Verify subprocess call
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    
    # Extract command from args
    cmd = args[0]
    assert cmd[0] == "gemini"
    assert cmd[1] == "-p"
    assert "SCV-Coder" in cmd[2]
    assert objective_id in cmd[2]
    
    # Verify redirection and detaching
    assert kwargs["stdout"] == mock_file
    assert kwargs["stderr"] == mock_file
    assert kwargs["start_new_session"] is True
    
    # Verify log file was closed in parent
    mock_file.close.assert_called_once()

@patch("subprocess.Popen")
@patch("os.makedirs")
@patch("builtins.open", new_callable=MagicMock)
def test_spawn_agent_scv_tester(mock_open, mock_makedirs, mock_popen):
    # Setup
    agent_name = "scv-tester"
    objective_id = "test-obj-456"
    
    # Mock file handle for telemetry
    mock_file = MagicMock()
    mock_open.return_value = mock_file
    
    # Execute
    spawn_agent(agent_name, objective_id)
    
    # Verify subprocess call
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    
    # Extract command from args
    cmd = args[0]
    assert cmd[0] == "gemini"
    assert cmd[1] == "-p"
    assert "SCV-Tester" in cmd[2]
    assert objective_id in cmd[2]

def test_spawn_agent_invalid_name():
    with pytest.raises(ValueError, match="Unknown agent name: invalid-agent"):
        spawn_agent("invalid-agent", "some-id")
