import pytest
from unittest.mock import patch, MagicMock
import json
import time
import os
import subprocess
from adjutant.engine import AdjutantHUD, run_adjutant_agent

@pytest.fixture
def mock_hud_deps():
    with patch("subprocess.check_output") as m_check_output, \
         patch("sys.stdout.write") as m_write, \
         patch("sys.stdout.flush") as m_flush, \
         patch("os.path.exists") as m_exists:
        yield {
            "check_output": m_check_output,
            "write": m_write,
            "flush": m_flush,
            "exists": m_exists
        }

def test_update_hud_success(mock_hud_deps):
    # Mock 'bd status --json' output
    mock_hud_deps["check_output"].return_value = json.dumps({
        "summary": {
            "total_issues": 10,
            "open_issues": 3,
            "closed_issues": 7,
            "in_progress_issues": 0
        }
    }).encode()
    
    mock_hud_deps["exists"].return_value = False
    
    hud = AdjutantHUD(mission="Test Mission")
    hud.update_hud()
    
    expected_title = "\033]0;Mission: Test Mission | 70.0% | 7/10 | Open: 3, IP: 0\007"
    mock_hud_deps["write"].assert_called_with(expected_title)
    mock_hud_deps["flush"].assert_called()

def test_update_hud_handles_subprocess_error(mock_hud_deps):
    mock_hud_deps["check_output"].side_effect = subprocess.CalledProcessError(1, ["bd", "status", "--json"])
    mock_hud_deps["exists"].return_value = False
    
    hud = AdjutantHUD(mission="Test Mission")
    hud.update_hud()
    
    expected_title = "\033]0;Mission: Test Mission | 0.0% | 0/0 | Open: 0, IP: 0\007"
    mock_hud_deps["write"].assert_called_with(expected_title)

@patch("adjutant.engine.get_active_scvs")
def test_update_hud_with_scvs(mock_get_scvs, mock_hud_deps):
    mock_hud_deps["check_output"].return_value = json.dumps({
        "summary": {
            "total_issues": 10,
            "open_issues": 3,
            "closed_issues": 7,
            "in_progress_issues": 0
        }
    }).encode()
    
    mock_get_scvs.return_value = {
        "adjutant-sjz.3": {"pid": 123},
        "adjutant-sjz.4": {"pid": 456}
    }
    
    hud = AdjutantHUD(mission="Test Mission")
    hud.update_hud()
    
    expected_title = "\033]0;Mission: Test Mission | 70.0% | 7/10 | Open: 3, IP: 0 | SCVs: 2 (sjz.3, sjz.4)\007"
    mock_hud_deps["write"].assert_called_with(expected_title)

def test_update_hud_edge_cases(mock_hud_deps):
    hud = AdjutantHUD(mission="Test Mission")

    # Case 1: 0 issues
    mock_hud_deps["check_output"].return_value = json.dumps({
        "summary": {"total_issues": 0, "open_issues": 0, "closed_issues": 0, "in_progress_issues": 0}
    }).encode()
    with patch("adjutant.engine.get_active_scvs", return_value={}):
        hud.update_hud()
        mock_hud_deps["write"].assert_called_with("\033]0;Mission: Test Mission | 0.0% | 0/0 | Open: 0, IP: 0\007")

    # Case 2: 100% closed
    mock_hud_deps["check_output"].return_value = json.dumps({
        "summary": {"total_issues": 5, "open_issues": 0, "closed_issues": 5, "in_progress_issues": 0}
    }).encode()
    with patch("adjutant.engine.get_active_scvs", return_value={}):
        hud.update_hud()
        mock_hud_deps["write"].assert_called_with("\033]0;Mission: Test Mission | 100.0% | 5/5 | Open: 0, IP: 0\007")

def test_hud_thread_lifecycle():
    with patch("adjutant.engine.AdjutantHUD.update_hud") as mock_update:
        hud = AdjutantHUD(mission="Test", interval=0.1)
        hud.start()
        assert hud.thread.is_alive()
        
        time.sleep(0.2)
        assert mock_update.called
        
        hud.stop()
        assert not hud.thread.is_alive()

@pytest.fixture
def mock_run_agent_deps():
    with patch("subprocess.run") as m_run, \
         patch("os.path.exists") as m_exists, \
         patch("os.remove") as m_remove, \
         patch("adjutant.engine.AdjutantHUD") as m_hud, \
         patch("adjutant.engine.SCVOverseer") as m_overseer, \
         patch("adjutant.engine.recover_orphaned_scvs") as m_recover, \
         patch("adjutant.engine.setup_logging") as m_setup_logging:
        yield {
            "run": m_run,
            "exists": m_exists,
            "remove": m_remove,
            "hud": m_hud,
            "overseer": m_overseer,
            "recover": m_recover,
            "setup_logging": m_setup_logging
        }

def test_run_adjutant_agent_uses_static_prompt(mock_run_agent_deps):
    mock_run_agent_deps["exists"].return_value = True
    run_adjutant_agent("Test mission")
    
    assert mock_run_agent_deps["run"].called
    args, kwargs = mock_run_agent_deps["run"].call_args
    env = kwargs.get("env")
    assert env is not None
    assert env["GEMINI_SYSTEM_MD"].endswith("adjutant/agents/adjutant/system.md")

def test_run_adjutant_agent_hud_integration(mock_run_agent_deps):
    mock_run_agent_deps["exists"].return_value = True
    mock_hud_instance = mock_run_agent_deps["hud"].return_value
    
    run_adjutant_agent("Test")
    
    mock_run_agent_deps["hud"].assert_called_once_with(mission="Test")
    mock_hud_instance.start.assert_called_once()
    mock_hud_instance.stop.assert_called_once()
    mock_run_agent_deps["recover"].assert_called_once()

def test_run_adjutant_agent_gemini_not_found(mock_run_agent_deps):
    mock_run_agent_deps["exists"].return_value = True
    mock_run_agent_deps["run"].side_effect = FileNotFoundError()
    
    with patch("sys.exit") as mock_exit, \
         patch("adjutant.engine.logger") as mock_logger, \
         patch("builtins.open", MagicMock()):
        run_adjutant_agent("Test")
    
    mock_exit.assert_called_with(1)
    mock_logger.info.assert_any_call("Error: 'gemini' CLI not found. Please ensure it is installed and in your PATH.")
    mock_run_agent_deps["recover"].assert_called_once()
