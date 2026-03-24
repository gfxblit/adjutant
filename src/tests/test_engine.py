import pytest
from unittest.mock import patch, mock_open
import json
import time
import subprocess
from adjutant.engine import AdjutantHUD, run_adjutant_agent

@pytest.fixture
def hud():
    return AdjutantHUD(mission="Test Mission")

@patch("subprocess.check_output")
@patch("sys.stdout.write")
@patch("sys.stdout.flush")
@patch("os.path.exists")
def test_update_hud_success(mock_exists, mock_flush, mock_write, mock_check_output, hud):
    # Mock 'bd status --json' output
    mock_check_output.return_value = json.dumps({
        "summary": {
            "total_issues": 10,
            "open_issues": 3,
            "closed_issues": 7,
            "in_progress_issues": 0
        }
    }).encode()
    
    # Mock registry doesn't exist for now
    mock_exists.return_value = False
    
    hud.update_hud()
    
    # Updated expected format: Mission: {MISSION} | {PROGRESS}% | {CLOSED}/{TOTAL} | Open: {OPEN}, IP: {IN_PROGRESS}
    expected_title = "\033]0;Mission: Test Mission | 70.0% | 7/10 | Open: 3, IP: 0\007"
    mock_write.assert_called_with(expected_title)
    mock_flush.assert_called()

@patch("subprocess.check_output")
@patch("sys.stdout.write")
@patch("os.path.exists")
def test_update_hud_handles_subprocess_error(mock_exists, mock_write, mock_check_output, hud):
    mock_check_output.side_effect = subprocess.CalledProcessError(1, ["bd", "status", "--json"])
    mock_exists.return_value = False
    
    # Should not raise exception
    hud.update_hud()
    # It still writes the title, just with 0% progress if bd fails
    expected_title = "\033]0;Mission: Test Mission | 0.0% | 0/0 | Open: 0, IP: 0\007"
    mock_write.assert_called_with(expected_title)

@patch("adjutant.engine.get_active_scvs")
@patch("subprocess.check_output")
@patch("sys.stdout.write")
def test_update_hud_with_scvs(mock_write, mock_check_output, mock_get_scvs, hud):
    # Mock 'bd status --json' output
    mock_check_output.return_value = json.dumps({
        "summary": {
            "total_issues": 10,
            "open_issues": 3,
            "closed_issues": 7,
            "in_progress_issues": 0
        }
    }).encode()
    
    # Mock get_active_scvs
    mock_get_scvs.return_value = {
        "adjutant-sjz.3": {"pid": 123},
        "adjutant-sjz.4": {"pid": 456}
    }
    
    hud.update_hud()
    
    # Expected title with SCVs: ... | SCVs: 2 (sjz.3, sjz.4)
    expected_title = "\033]0;Mission: Test Mission | 70.0% | 7/10 | Open: 3, IP: 0 | SCVs: 2 (sjz.3, sjz.4)\007"
    mock_write.assert_called_with(expected_title)

@patch("adjutant.engine.get_active_scvs")
@patch("subprocess.check_output")
@patch("sys.stdout.write")
def test_update_hud_edge_cases(mock_write, mock_check_output, mock_get_scvs, hud):
    mock_get_scvs.return_value = {}

    # Case 1: 0 issues
    mock_check_output.return_value = json.dumps({
        "summary": {"total_issues": 0, "open_issues": 0, "closed_issues": 0, "in_progress_issues": 0}
    }).encode()
    hud.update_hud()
    mock_write.assert_called_with("\033]0;Mission: Test Mission | 0.0% | 0/0 | Open: 0, IP: 0\007")

    # Case 2: 100% closed
    mock_check_output.return_value = json.dumps({
        "summary": {"total_issues": 5, "open_issues": 0, "closed_issues": 5, "in_progress_issues": 0}
    }).encode()
    hud.update_hud()
    mock_write.assert_called_with("\033]0;Mission: Test Mission | 100.0% | 5/5 | Open: 0, IP: 0\007")

def test_hud_thread_lifecycle():
    with patch("adjutant.engine.AdjutantHUD.update_hud") as mock_update:
        hud = AdjutantHUD(mission="Test", interval=0.1)
        hud.start()
        assert hud.thread.is_alive()
        
        # Wait a bit for at least one update
        time.sleep(0.2)
        assert mock_update.called
        
        hud.stop()
        assert not hud.thread.is_alive()

@patch("subprocess.run")
@patch("os.path.exists")
@patch("os.remove")
@patch("adjutant.engine.AdjutantHUD")
@patch("adjutant.engine.SCVOverseer")
@patch("adjutant.engine.recover_orphaned_scvs")
@patch("adjutant.engine.setup_logging")
def test_run_adjutant_agent_uses_static_prompt(mock_setup_logging, mock_recover, mock_overseer_class, mock_hud_class, mock_remove, mock_exists, mock_run):
    mock_exists.return_value = True
    directive = "Test mission"
    
    run_adjutant_agent(directive)
    
    # Verify subprocess.run was called with correct environment
    assert mock_run.called
    args, kwargs = mock_run.call_args
    env = kwargs.get("env")
    assert env is not None
    assert env["GEMINI_SYSTEM_MD"].endswith("adjutant/agents/adjutant/system.md")

@patch("subprocess.run")
@patch("os.path.exists")
@patch("os.remove")
@patch("adjutant.engine.AdjutantHUD")
@patch("adjutant.engine.SCVOverseer")
@patch("adjutant.engine.recover_orphaned_scvs")
@patch("adjutant.engine.setup_logging")
def test_run_adjutant_agent_hud_integration(mock_setup_logging, mock_recover, mock_overseer_class, mock_hud_class, mock_remove, mock_exists, mock_run):
    mock_exists.return_value = True
    mock_hud_instance = mock_hud_class.return_value
    
    run_adjutant_agent("Test")
    
    mock_hud_class.assert_called_once_with(mission="Test")
    mock_hud_instance.start.assert_called_once()
    mock_hud_instance.stop.assert_called_once()
    mock_recover.assert_called_once()

@patch("subprocess.run")
@patch("os.path.exists")
@patch("os.remove")
@patch("adjutant.engine.AdjutantHUD")
@patch("adjutant.engine.SCVOverseer")
@patch("adjutant.engine.recover_orphaned_scvs")
@patch("adjutant.engine.setup_logging")
@patch("adjutant.engine.logger")
def test_run_adjutant_agent_gemini_not_found(mock_logger, mock_setup_logging, mock_recover, mock_overseer_class, mock_hud_class, mock_remove, mock_exists, mock_run):
    mock_exists.return_value = True
    mock_run.side_effect = FileNotFoundError()
    
    with pytest.raises(SystemExit) as excinfo:
        # Mocking open to avoid file system interaction
        with patch("builtins.open", mock_open(read_data="template")):
            run_adjutant_agent("Test")
    
    assert excinfo.value.code == 1
    mock_logger.info.assert_any_call("Error: 'gemini' CLI not found. Please ensure it is installed and in your PATH.")
    mock_recover.assert_called_once()
