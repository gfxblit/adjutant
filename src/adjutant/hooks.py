import subprocess
import json

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
        closed_objectives.sort(key=lambda x: x.get("closed_at", ""), reverse=True)
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
