import subprocess
import json
import sys

def get_mission_telemetry():
    """
    Returns a formatted string containing current open objectives and recent activity summary.
    """
    try:
        # Get open objectives
        open_output = subprocess.check_output(["bd", "list", "--status", "open", "--json"], stderr=subprocess.DEVNULL)
        open_objectives = json.loads(open_output)
        
        # Get in-progress objectives
        ip_output = subprocess.check_output(["bd", "list", "--status", "in_progress", "--json"], stderr=subprocess.DEVNULL)
        ip_objectives = json.loads(ip_output)
        
        all_active = ip_objectives + open_objectives
        
        # Get recently closed objectives for activity summary
        closed_output = subprocess.check_output(["bd", "list", "--status", "closed", "--json"], stderr=subprocess.DEVNULL)
        closed_objectives = json.loads(closed_output)
        # Sort by closed_at descending if available, otherwise just take last 5
        closed_objectives.sort(key=lambda x: x.get("closed_at") or "", reverse=True)
        recent_closed = closed_objectives[:5]
        
        telemetry = "## Mission Telemetry\n\n"
        
        telemetry += "### Active Objectives\n"
        if not all_active:
            telemetry += "- No active objectives.\n"
        for obj in all_active:
            status_str = f" [{obj.get('status')}]" if obj.get('status') != 'open' else ""
            telemetry += f"- {obj.get('id')}: {obj.get('title')}{status_str}\n"
            
        telemetry += "\n### Recent Activity\n"
        if not recent_closed:
            telemetry += "- No recent activity.\n"
        for obj in recent_closed:
            telemetry += f"- COMPLETED: {obj.get('id')}: {obj.get('title')}\n"
            
        return telemetry
    except Exception:
        return "Mission telemetry unavailable"

def main():
    """
    CLI entry point for the Gemini hook protocol.
    Reads JSON from stdin, gathers telemetry, and writes JSON response to stdout.
    """
    try:
        # Read JSON from stdin
        # Gemini's BeforeAgent hook provides mission info, but we don't strictly need it yet
        # for telemetry as we pull it from bd locally.
        input_data = sys.stdin.read()
        if input_data:
            json.loads(input_data)
        
        telemetry = get_mission_telemetry()
        
        # Gemini hook protocol response for BeforeAgent
        output_data = {
            "hookSpecificOutput": {
                "additionalContext": telemetry
            }
        }
        
        sys.stdout.write(json.dumps(output_data))
        sys.stdout.flush()
    except Exception as e:
        # In case of error, output empty context but don't crash
        output_data = {
            "hookSpecificOutput": {
                "additionalContext": f"Telemetry error: {str(e)}"
            }
        }
        sys.stdout.write(json.dumps(output_data))
        sys.stdout.flush()

if __name__ == "__main__":
    main()
