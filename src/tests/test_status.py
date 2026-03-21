import json
import os
import subprocess
from unittest.mock import patch, mock_open

import pytest

from adjutant.engine import get_project_root, show_status

def test_get_project_root():
    root = get_project_root()
    assert isinstance(root, str)
    assert os.path.exists(root)

@patch("subprocess.check_output")
@patch("builtins.print")
@patch("os.kill")
def test_show_status(mock_kill, mock_print, mock_check_output):
    mock_kill.return_value = None
    # Mock bd status output
    status_output = json.dumps({
        "summary": {
            "total_issues": 10,
            "open_issues": 2,
            "in_progress_issues": 3,
            "closed_issues": 5
        }
    })
    
    # Mock bd list output
    list_output = json.dumps([
        {
            "id": "obj-1",
            "title": "Objective 1",
            "status": "in_progress"
        },
        {
            "id": "obj-2",
            "title": "Objective 2",
            "status": "open"
        }
    ])
    
    mock_check_output.side_effect = [status_output, list_output]
    
    # Mock registry
    registry_data = json.dumps({
        "obj-1": {
            "pid": 1234,
            "agent_name": "scv-coder",
            "model": "gemini-3.1-pro-preview"
        }
    })
    
    mission_path = os.path.join(get_project_root(), ".beads", "telemetry", "active_mission.txt")
    
    def exists_side_effect(path):
        if path == mission_path: return True
        return True # for registry check
    
    def open_side_effect(path, mode="r"):
        if path == mission_path:
            return mock_open(read_data="Test Mission Directive")()
        return mock_open(read_data=registry_data)()
    
    with patch("os.path.exists", side_effect=exists_side_effect):
        with patch("builtins.open", side_effect=open_side_effect):
            show_status()
            
    # Check if print was called with expected strings
    mock_print.assert_any_call("=== Adjutant Status ===")
    mock_print.assert_any_call("Mission: Test Mission Directive")
    mock_print.assert_any_call("\nMission Progress: 50.0% (5/10 issues closed)")
    mock_print.assert_any_call("Open: 2 | In Progress: 3")
    mock_print.assert_any_call("\n--- Active Objectives ---")
    mock_print.assert_any_call("[obj-1] Objective 1")
    mock_print.assert_any_call("\n--- Running SCVs ---")
    mock_print.assert_any_call("[obj-1] Agent: scv-coder | PID: 1234 | Status: Running | Model: gemini-3.1-pro-preview")
