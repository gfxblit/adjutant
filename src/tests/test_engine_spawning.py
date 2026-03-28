import pytest
from unittest.mock import patch, MagicMock
import os
import json
from adjutant.engine import spawn_agent

# Constants for testing
CODER_PROMPT = "Coder Prompt for {objective_id}"
TESTER_PROMPT = "Tester Prompt for {objective_id}"

@pytest.fixture
def mock_fs():
    """Provides a consistent way to mock file system operations."""
    with patch("os.path.exists") as m_exists, \
         patch("os.makedirs") as m_makedirs, \
         patch("builtins.open") as m_open:
        m_exists.return_value = True
        yield {"exists": m_exists, "makedirs": m_makedirs, "open": m_open}

@pytest.fixture
def mock_subp():
    """Provides a consistent way to mock subprocess operations."""
    with patch("subprocess.run") as m_run, \
         patch("subprocess.Popen") as m_popen, \
         patch("subprocess.check_output") as m_check_output:
        m_popen.return_value.pid = 12345
        m_check_output.return_value = b"/mock/git"
        yield {"run": m_run, "popen": m_popen, "check_output": m_check_output}

@pytest.fixture
def mock_engine_core():
    """Provides a consistent way to mock engine's core dependencies."""
    if "TMUX" in os.environ:
        os.environ.pop("TMUX")
        
    with patch("adjutant.engine.get_project_root") as m_get_root, \
         patch("adjutant.engine.timezone") as m_timezone, \
         patch("adjutant.engine.datetime") as m_datetime:
        m_get_root.return_value = "/mock/project"
        m_datetime.now.return_value.isoformat.return_value = "2026-03-24T12:00:00+00:00"
        m_timezone.utc = MagicMock()
        yield {
            "get_root": m_get_root,
            "timezone": m_timezone,
            "datetime": m_datetime,
            "root": "/mock/project",
            "isoformat": "2026-03-24T12:00:00+00:00"
        }

@pytest.fixture
def agent_files(mock_fs):
    """Provides a managed dictionary of mocked files for open()."""
    files = {}
    def open_side_effect(path, mode='r', **kwargs):
        if path not in files:
            m = MagicMock(name=path)
            m.__enter__.return_value = m
            files[path] = m
        m = files[path]
        if 'r' in mode:
            if "scv-coder" in path:
                m.read.return_value = CODER_PROMPT
            elif "scv-tester" in path:
                m.read.return_value = TESTER_PROMPT
        return m
    mock_fs["open"].side_effect = open_side_effect
    return files

def verify_spawn_basics(mock_subp, agent_files, project_root, objective_id, agent_name, isoformat, expected_prompt, expected_directive="Execute mission."):
    """Helper to verify the basic actions taken by spawn_agent."""
    # 1. Verify bd update status
    mock_subp["run"].assert_any_call(
        ["bd", "update", objective_id, "--status", "in_progress"],
        check=False,
        capture_output=True
    )

    # 2. Verify bd worktree create
    worktree_path = os.path.join(project_root, ".adjutant", "worktrees", objective_id)
    mock_subp["run"].assert_any_call(
        ["bd", "worktree", "create", worktree_path, "--branch", f"scv/{objective_id}"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True
    )

    # 3. Verify .beads/redirect creation
    redirect_path = os.path.join(worktree_path, ".beads", "redirect")
    assert redirect_path in agent_files
    agent_files[redirect_path].write.assert_called_once_with(os.path.join(project_root, ".beads"))

    # 4. Verify Log file writing
    log_path = os.path.join(project_root, ".adjutant", "logs", f"{objective_id}.log")
    assert log_path in agent_files
    log_handle = agent_files[log_path]
    all_writes = "".join(call[0][0] for call in log_handle.write.call_args_list)
    assert f"SCV SPAWN: {isoformat}" in all_writes
    assert f"AGENT: {agent_name}" in all_writes
    assert expected_prompt in all_writes

    # 5. Verify Subprocess Popen
    mock_subp["popen"].assert_called_once()
    args, kwargs = mock_subp["popen"].call_args
    cmd = args[0]
    assert cmd[0] == "gemini"
    assert kwargs["cwd"] == worktree_path
    assert "--yolo" in cmd
    assert "--include-directories" in cmd
    assert project_root in cmd
    assert "-p" in cmd
    assert kwargs["stdout"] == log_handle
    assert kwargs["stderr"] == log_handle

    # 6. Verify .scv_info.json writing
    scv_info_path = os.path.join(worktree_path, ".scv_info.json")
    assert scv_info_path in agent_files
    info_handle = agent_files[scv_info_path]
    info_content = "".join(call[0][0] for call in info_handle.write.call_args_list)
    info_data = json.loads(info_content)
    assert info_data["pid"] == 12345
    assert info_data["directive"] == expected_directive
    return cmd

def test_spawn_agent_comprehensive(mock_engine_core, agent_files, mock_subp):
    agent_name = "scv-coder"
    objective_id = "test-obj-123"
    project_root = mock_engine_core["root"]
    
    # Execute
    spawn_agent(agent_name, objective_id)

    cmd = verify_spawn_basics(
        mock_subp, agent_files, project_root, objective_id, agent_name, 
        mock_engine_core["isoformat"], CODER_PROMPT
    )
    
    prompt_idx = cmd.index("-p") + 1
    assert f"Objective ID: {objective_id}" in cmd[prompt_idx]
    assert "Execute mission." in cmd[prompt_idx]

def test_spawn_agent_custom_model_and_directive(mock_engine_core, agent_files, mock_subp):
    agent_name = "scv-tester"
    objective_id = "test-obj-456"
    custom_model = "gemini-2.5-flash-lite"
    custom_directive = "Test this code thoroughly."
    project_root = mock_engine_core["root"]

    # Execute
    spawn_agent(agent_name, objective_id, starting_model=custom_model, directive=custom_directive)

    cmd = verify_spawn_basics(
        mock_subp, agent_files, project_root, objective_id, agent_name, 
        mock_engine_core["isoformat"], TESTER_PROMPT, expected_directive=custom_directive
    )
    
    assert "--model" in cmd
    assert custom_model in cmd
    prompt_idx = cmd.index("-p") + 1
    assert f"Objective ID: {objective_id}" in cmd[prompt_idx]
    assert custom_directive in cmd[prompt_idx]

def test_spawn_agent_invalid_name(mock_fs):
    mock_fs["exists"].return_value = False
    with pytest.raises(ValueError, match="Unknown agent or missing system prompt: invalid-agent"):
        spawn_agent("invalid-agent", "some-id")
