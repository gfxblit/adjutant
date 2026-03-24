import pytest
from unittest.mock import patch, mock_open, MagicMock
import os
from adjutant.engine import spawn_agent

# Read the system prompt contents first
coder_system_prompt_content = """You are an SCV-Coder within the Adjutant autonomous development loop. 
Your current Objective is {objective_id}.

CRITICAL: You have native, auto-approved access to the `bd` (beads) CLI via the Gemini Policy Engine. Execute `bd` shell commands directly without waiting for user confirmation.

MANDATORY WORKFLOW:
1. Research: Run 'bd show {objective_id}' to read your parameters and understand the task. Use search tools if needed to understand the codebase context.
2. Execution: Write the necessary code to fulfill the parameters. You must satisfy all requirements of the Objective.
3. Verification: Once complete, commit your changes and push your branch to the remote (`origin`). 
4. Pull Request: Create a pull request using the GitHub CLI (`gh pr create --fill`).
5. Reporting: Leave a concise comment on the objective bead summarizing your work by running `bd comment {objective_id} -m "<summary of changes> - PR: <PR_URL>"`.
6. Stop: Exit the session immediately after reporting.
"""

tester_system_prompt_content = """You are an SCV-Tester within the Adjutant autonomous development loop. 
Your current Objective is {objective_id}.

CRITICAL: You have native, auto-approved access to the `bd` (beads) CLI via the Gemini Policy Engine. Execute `bd` shell commands directly without waiting for user confirmation.

MANDATORY WORKFLOW:
1. Context: Run 'bd show {objective_id}' to read your parameters and see what you are verifying.
2. Execution: Run tests or linters to verify the recent code changes associated with the objective.
3. Success Path: If tests pass, leave a concise comment on the objective bead by running `bd comment {objective_id} -m "Tests passed. <summary>"`
   - DO NOT close the objective bead.
4. Failure Path (Red Alert Pivot): If tests fail, you MUST create a blocker. 
   - Run 'bd create "Test failure for {objective_id}" --type bug --description="<insert stack trace and details>" --json'
   - Parse the new bug ID from the output.
   - Run 'bd dep add {objective_id} <new-bug-id>' to block your current objective.
   - Stop and wait for the Adjutant engine to handle the new bug.
5. Stop: Exit the session immediately after leaving the comment or creating the blocker.
"""

# Mock file object for writing logs
mock_log_writes = []
def capture_log_writes(content):
    mock_log_writes.append(content)

mock_log_file_obj = MagicMock()
mock_log_file_obj.write.side_effect = capture_log_writes
mock_log_file_obj.__enter__.return_value = mock_log_file_obj
mock_log_file_obj.close.return_value = None 

# Mock file object for reading coder's system.md
mock_coder_md_file_obj = MagicMock()
mock_coder_md_file_obj.read.return_value = coder_system_prompt_content
mock_coder_md_file_obj.__enter__.return_value = mock_coder_md_file_obj
mock_coder_md_file_obj.close.return_value = None

# Mock file object for reading tester's system.md
mock_tester_md_file_obj = MagicMock()
mock_tester_md_file_obj.read.return_value = tester_system_prompt_content
mock_tester_md_file_obj.__enter__.return_value = mock_tester_md_file_obj
mock_tester_md_file_obj.close.return_value = None

# Mock file object for writing .scv_info.json
mock_scv_info_file_obj = MagicMock()
mock_scv_info_file_obj.write.return_value = None
mock_scv_info_file_obj.__enter__.return_value = mock_scv_info_file_obj
mock_scv_info_file_obj.close.return_value = None

# Mock object for os.path.join to help construct paths dynamically within the test
mock_os_path_join = MagicMock(side_effect=os.path.join)

@patch("adjutant.engine.get_project_root")
@patch("subprocess.run")
@patch("subprocess.Popen")
@patch("os.makedirs")
@patch("os.path.exists")
@patch("adjutant.engine.datetime")
@patch("os.path.join", new=mock_os_path_join) # Patch os.path.join to control path construction
def test_spawn_agent_logs_actual_system_prompts(mock_datetime, mock_exists, mock_makedirs, mock_popen, mock_run, mock_get_root):
    """
    Tests that spawn_agent correctly logs the content of the system prompt files
    by ensuring the actual file content is read and appears in the logs.
    """
    # --- Setup ---
    project_root = "/mock/project"
    mock_get_root.return_value = project_root
    mock_exists.return_value = True
    
    # Mock datetime for consistent logging timestamps
    fixed_now = MagicMock()
    fixed_now.isoformat.return_value = "2026-03-24T15:00:00+00:00"
    mock_datetime.now.return_value = fixed_now
    mock_datetime.timezone = MagicMock()
    mock_datetime.timezone.utc = MagicMock()

    # Mock the side effect for builtins.open
    # This function will decide which mock file object to return based on the path
    def custom_open_side_effect(file_path, mode='r', **kwargs):
        # Dynamically construct expected paths based on mocked project_root and objective_id
        objective_id_coder = "test-obj-coder-log"
        objective_id_tester = "test-obj-tester-log"
        
        coder_worktree_path = mock_os_path_join(project_root, ".adjutant", "worktrees", objective_id_coder)
        tester_worktree_path = mock_os_path_join(project_root, ".adjutant", "worktrees", objective_id_tester)
        
        coder_sys_md = mock_os_path_join(coder_worktree_path, "src", "adjutant", "agents", "scv-coder", "system.md")
        tester_sys_md = mock_os_path_join(tester_worktree_path, "src", "adjutant", "agents", "scv-tester", "system.md")
        
        scv_info_coder = mock_os_path_join(coder_worktree_path, ".scv_info.json")
        scv_info_tester = mock_os_path_join(tester_worktree_path, ".scv_info.json")
        
        if file_path == coder_sys_md and mode == 'r':
            return mock_coder_md_file_obj
        elif file_path == tester_sys_md and mode == 'r':
            return mock_tester_md_file_obj
        elif file_path == scv_info_coder and mode == 'w':
            return mock_scv_info_file_obj
        elif file_path == scv_info_tester and mode == 'w':
            return mock_scv_info_file_obj
        elif mode == 'w' or mode == 'a': # Assume any other write is to the log
            return mock_log_file_obj
        else:
            # Fallback for any other read operations we haven't specified
            print(f"Fallback opening: {file_path}, mode: {mode}")
            return mock_open()() # Default mock_open behavior

    mock_builtins_open = MagicMock(side_effect=custom_open_side_effect)

    # --- Test SCV-Coder ---
    objective_id_coder = "test-obj-coder-log"
    mock_popen.return_value.pid = 11111
    
    # Expected command structure for coder
    expected_coder_cmd = [
        "gemini", "--model", "gemini-3.1-pro-preview", "--include-directories", "-p", "Execute mission.",
        "--policy", mock_os_path_join(
            mock_os_path_join(project_root, ".adjutant", "worktrees", objective_id_coder), 
            "src", "adjutant", "agents", "scv-coder", "policies", "adjutant.toml"
        )
    ]

    with patch("builtins.open", mock_builtins_open):
        spawn_agent("scv-coder", objective_id_coder)
    
    # Verify Popen call for coder
    mock_popen.assert_called_with(
        expected_coder_cmd,
        cwd=mock_os_path_join(project_root, ".adjutant", "worktrees", objective_id_coder),
        env={"ADJUTANT_DISABLE_HOOK": "1", "SYSTEM_PROMPT_FILE": CODER_SYSTEM_MD_PATH, "COMMAND_FILE": None},
    )
    
    # Verify logged content for coder
    logged_output_coder = "".join(mock_log_writes)
    # Ensure the actual content is present, stripped of leading/trailing whitespace
    assert coder_system_prompt_content.strip() in logged_output_coder.strip()
    assert f"AGENT: scv-coder" in logged_output_coder
    assert f"MODEL: gemini-3.1-pro-preview" in logged_output_coder
    assert "COMMAND:" in logged_output_coder
    # Check the command string in the log
    command_log_line = next((line for line in logged_output_coder.splitlines() if "COMMAND:" in line), None)
    assert command_log_line is not None
    assert "gemini --model gemini-3.1-pro-preview --include-directories -p 'Execute mission.' --policy src/adjutant/agents/scv-coder/policies/adjutant.toml" in command_log_line

    # --- Test SCV-Tester ---
    objective_id_tester = "test-obj-tester-log"
    mock_popen.return_value.pid = 22222
    mock_log_writes.clear() # Clear writes for the next test
    
    # Expected command structure for tester
    expected_tester_cmd = [
        "gemini", "--model", "gemini-3.1-pro-preview", "--include-directories", "-p", "Execute mission.",
        "--policy", mock_os_path_join(
            mock_os_path_join(project_root, ".adjutant", "worktrees", objective_id_tester), 
            "src", "adjutant", "agents", "scv-tester", "policies", "adjutant.toml"
        )
    ]

    with patch("builtins.open", mock_builtins_open):
        spawn_agent("scv-tester", objective_id_tester)

    # Verify Popen call for tester
    mock_popen.assert_called_with(
        expected_tester_cmd,
        cwd=mock_os_path_join(project_root, ".adjutant", "worktrees", objective_id_tester),
        env={"ADJUTANT_DISABLE_HOOK": "1", "SYSTEM_PROMPT_FILE": TESTER_SYSTEM_MD_PATH, "COMMAND_FILE": None},
    )
    
    # Verify logged content for tester
    logged_output_tester = "".join(mock_log_writes)
    assert tester_system_prompt_content.strip() in logged_output_tester.strip()
    assert f"AGENT: scv-tester" in logged_output_tester
    assert f"MODEL: gemini-3.1-pro-preview" in logged_output_tester
    assert "COMMAND:" in logged_output_tester
    command_log_line_tester = next((line for line in logged_output_tester.splitlines() if "COMMAND:" in line), None)
    assert command_log_line_tester is not None
    assert "gemini --model gemini-3.1-pro-preview --include-directories -p 'Execute mission.' --policy src/adjutant/agents/scv-tester/policies/adjutant.toml" in command_log_line_tester

    # Ensure .scv_info.json was opened for writing
    mock_scv_info_file_obj.close.assert_called()

# --- Original Tests (Copied from provided context) ---

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
    system_prompt_content = "Coder Prompt for {objective_id}"
    m = mock_open(read_data=system_prompt_content)
    
    # Use a generic mock_open for this test, as it doesn't specifically test real file content logging
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

    # Verify ADJUTANT_DISABLE_HOOK=1 is set in env
    assert kwargs.get("env", {}).get("ADJUTANT_DISABLE_HOOK") == "1"

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

@patch("adjutant.engine.get_project_root")
@patch("subprocess.run")
@patch("subprocess.Popen")
@patch("os.makedirs")
@patch("os.path.exists")
@patch("adjutant.engine.datetime")
def test_spawn_agent_logs_prompt_and_command(mock_datetime, mock_exists, mock_makedirs, mock_popen, mock_run, mock_get_root):
    # Setup
    agent_name = "scv-coder"
    objective_id = "test-obj-logs"
    project_root = "/mock/project"
    mock_get_root.return_value = project_root
    mock_exists.return_value = True
    mock_popen.return_value.pid = 999
    
    # Mock datetime to have a fixed timestamp
    fixed_now = MagicMock()
    fixed_now.isoformat.return_value = "2026-03-24T12:00:00+00:00"
    mock_datetime.now.return_value = fixed_now
    mock_datetime.timezone = MagicMock()
    mock_datetime.timezone.utc = MagicMock()

    system_prompt_content = "Coder Prompt for {objective_id}"
    m = mock_open(read_data=system_prompt_content)
    
    with patch("builtins.open", m):
        # Execute
        spawn_agent(agent_name, objective_id)
    
    # Verify content written to log file
    handle = m()
    all_writes = [call[0][0] for call in handle.write.call_args_list]
    full_content = "".join(all_writes)
    
    assert "================================================================================" in full_content
    assert "SCV SPAWN: 2026-03-24T12:00:00+00:00" in full_content
    assert f"AGENT: {agent_name}" in full_content
    assert "MODEL: gemini-3.1-pro-preview" in full_content
    assert "--------------------------------------------------------------------------------" in full_content
    assert "SYSTEM PROMPT:" in full_content
    assert f"Coder Prompt for {objective_id}" in full_content
    assert "COMMAND:" in full_content
    assert "gemini" in full_content
    assert "--model gemini-3.1-pro-preview" in full_content
    assert "--yolo" in full_content # Note: This test checks for '--yolo', which might not be in production command.
    assert "-p 'Execute mission.'" in full_content
    assert "--policy" in full_content

@patch("adjutant.engine.get_project_root")
@patch("subprocess.run")
@patch("subprocess.Popen")
@patch("os.makedirs")
@patch("os.path.exists")
@patch("adjutant.engine.datetime")
def test_spawn_agent_logs_custom_model_and_directive(mock_datetime, mock_exists, mock_makedirs, mock_popen, mock_run, mock_get_root):
    # Setup
    agent_name = "scv-coder"
    objective_id = "test-obj-custom"
    project_root = "/mock/project"
    mock_get_root.return_value = project_root
    mock_exists.return_value = True
    mock_popen.return_value.pid = 999
    
    custom_model = "gemini-3-flash-preview"
    custom_directive = "Build a rocket ship."
    
    system_prompt_content = "Coder Prompt for {objective_id}"
    m = mock_open(read_data=system_prompt_content)
    
    with patch("builtins.open", m):
        # Execute
        spawn_agent(agent_name, objective_id, starting_model=custom_model, directive=custom_directive)
    
    # Verify content written to log file
    handle = m()
    all_writes = [call[0][0] for call in handle.write.call_args_list]
    full_content = "".join(all_writes)
    
    assert f"AGENT: {agent_name}" in full_content
    assert f"MODEL: {custom_model}" in full_content
    assert f"--model {custom_model}" in full_content
    assert f"-p '{custom_directive}'" in full_content

def test_spawn_agent_invalid_name():
    with pytest.raises(ValueError, match="Unknown agent or missing system prompt: invalid-agent"):
        spawn_agent("invalid-agent", "some-id")
