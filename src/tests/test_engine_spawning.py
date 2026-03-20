from unittest.mock import patch, mock_open
from adjutant.engine import spawn_agent
import pytest

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
    # 2. Writing log file
    system_prompt_content = "Coder Prompt for {objective_id}"
    m = mock_open(read_data=system_prompt_content)
    
    with patch("builtins.open", m):
        # Execute
        spawn_agent(agent_name, objective_id)
    
    # Verify telemetry directory creation
    assert any(call[0][0].endswith(".beads/telemetry") for call in mock_makedirs.call_args_list)
    
    # Verify open calls
    # First call: read system.md
    assert m.call_args_list[0][0][0].endswith("adjutant/agents/scv-coder/system.md")
    assert m.call_args_list[0][0][1] == "r"

    # Second call: write resolved system prompt
    assert m.call_args_list[1][0][0].endswith(f".resolved_system_{objective_id}.md")
    assert m.call_args_list[1][0][1] == "w"

    # Third call: write log file
    assert m.call_args_list[2][0][0].endswith(f"{objective_id}.log")
    assert m.call_args_list[2][0][1] == "a"    # Verify subprocess call
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    
    # Extract command from args
    cmd = args[0]
    assert cmd[0] == "gemini"
    assert "--model" in cmd
    assert "gemini-3.1-pro-preview" in cmd
    assert "-p" in cmd
    assert "Execute mission." in cmd

    # Verify cwd is set to worktree
    assert kwargs.get("cwd", "").endswith(f"worktrees/{objective_id}")

    # Verify environment variables
    env = kwargs.get("env", {})
    assert env.get("GEMINI_SYSTEM_MD", "").endswith(f".resolved_system_{objective_id}.md")    
    # Verify redirection and detaching
    # mock_open() returns the file handle
    mock_file = m.return_value
    assert kwargs["stdout"] == mock_file
    assert kwargs["stderr"] == mock_file
    assert kwargs["start_new_session"] is True
    
    # Verify log file was closed in parent
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
    assert "--model" in cmd
    assert "gemini-3.1-pro-preview" in cmd
    assert "-p" in cmd
    assert "Execute mission." in cmd

    # Verify environment variables
    env = kwargs.get("env", {})
    assert env.get("GEMINI_SYSTEM_MD", "").endswith(f".resolved_system_{objective_id}.md")

def test_spawn_agent_invalid_name():
    with pytest.raises(ValueError, match="Unknown agent or missing system prompt: invalid-agent"):
        spawn_agent("invalid-agent", "some-id")
