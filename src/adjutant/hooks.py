import subprocess
import json
import sys
import os

def get_mission_telemetry():
    """
    Returns a formatted string containing current open objectives and recent activity summary.
    """
    if os.environ.get("ADJUTANT_DISABLE_HOOK") == "1":
        return ""
    try:
        # Get all issues in one call for better performance and to reduce potential timeout issues
        output = subprocess.check_output(["bd", "list", "--all", "--json"], stderr=subprocess.DEVNULL, timeout=5.0)
        all_issues = json.loads(output)

        open_objectives = [i for i in all_issues if i.get("status") == "open"]
        ip_objectives = [i for i in all_issues if i.get("status") == "in_progress"]
        closed_objectives = [i for i in all_issues if i.get("status") == "closed"]

        all_active = ip_objectives + open_objectives

        # Sort by closed_at descending if available, otherwise just take last 5
        closed_objectives.sort(key=lambda x: x.get("closed_at", ""), reverse=True)
        recent_closed = closed_objectives[:5]

        # PR Tracking Logic
        pr_info = {} # dict mapping objective id to list of PR statuses
        if all_active:
            try:
                import re
                url_pattern = re.compile(r'https://github\.com/[^\s/]+/[^\s/]+/pull/\d+')
                active_ids = [obj.get("id") for obj in all_active if obj.get("id")]
                
                show_output = subprocess.check_output(
                    ["bd", "show", "--json"] + active_ids,
                    stderr=subprocess.DEVNULL, timeout=5.0
                )
                show_details = json.loads(show_output)
                if not isinstance(show_details, list):
                    show_details = [show_details]
                
                urls_to_ids = {} # map url -> set of objective ids
                for detail in show_details:
                    obj_id = detail.get("id")
                    for comment in detail.get("comments", []):
                        body = comment.get("text", "")
                        found_urls = url_pattern.findall(body)
                        for url in found_urls:
                            urls_to_ids.setdefault(url, set()).add(obj_id)
                
                if urls_to_ids:
                    gh_output = subprocess.check_output(
                        ["gh", "pr", "list", "--state", "all", "--json", "url,state,number"],
                        stderr=subprocess.DEVNULL, timeout=5.0
                    )
                    gh_prs = json.loads(gh_output)
                    url_to_gh_pr = {pr["url"]: pr for pr in gh_prs}
                    
                    for url, ids in urls_to_ids.items():
                        if url in url_to_gh_pr:
                            pr_data = url_to_gh_pr[url]
                            status_str = f"PR #{pr_data['number']} {pr_data['state']}"
                            for obj_id in ids:
                                pr_info.setdefault(obj_id, []).append(status_str)
            except Exception:
                # Silently ignore errors in PR tracking
                pass
        
        telemetry = "## Mission Telemetry\n\n"
        
        telemetry += "### Active Objectives\n"
        if not all_active:
            telemetry += "- No active objectives.\n"
        for obj in all_active:
            status_str = f" [{obj.get('status')}]" if obj.get('status') != 'open' else ""
            
            obj_id = obj.get("id")
            if obj_id in pr_info and pr_info[obj_id]:
                pr_str = ", ".join(pr_info[obj_id])
                status_str += f" [{pr_str}]"
                
            telemetry += f"- {obj_id}: {obj.get('title')}{status_str}\n"
            
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
        if os.environ.get("ADJUTANT_DISABLE_HOOK") == "1":
            # Early exit for disabled hook
            sys.stdout.write(json.dumps({"hookSpecificOutput": {}}))
            sys.stdout.flush()
            return

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
