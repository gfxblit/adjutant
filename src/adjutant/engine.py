import os
import subprocess
import sys

def run_adjutant_agent(initial_directive: str):
    """
    Launches the Adjutant (Planner) agent as an interactive Gemini session.
    The Adjutant's specialized persona is injected via GEMINI_SYSTEM_MD.
    """
    print(f"\n[Adjutant Online: Initiating Mission Planning]")
    
    # Resolve the path to the Adjutant's system prompt
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    system_prompt_path = os.path.join(base_dir, "adjutant", "adjutant_system.md")
    
    # Read the base system prompt
    with open(system_prompt_path, "r") as f:
        system_prompt = f.read()

    # Define the sub-agent tools documentation for the prompt
    # In a real implementation, these would be actual executable tools,
    # but for this bootstrap we'll describe them as available via the engine.
    sub_agents_doc = """
### Available Sub-Agents (Tools)
- **scv_coder(objective_id: str, instructions: str)**: Deploys a coding agent to fulfill a specific objective.
- **scv_tester(objective_id: str, instructions: str)**: Deploys a testing agent to verify an objective.
"""
    
    # Simple template replacement
    system_prompt = system_prompt.replace("${SubAgents}", sub_agents_doc)
    system_prompt = system_prompt.replace("${AgentSkills}", "") # Reserved for future use

    # Write the resolved prompt to a temporary file for the session
    temp_prompt_path = os.path.join(base_dir, ".adjutant_resolved_system.md")
    with open(temp_prompt_path, "w") as f:
        f.write(system_prompt)
    
    # Configure the environment to override the system prompt
    env = os.environ.copy()
    env["GEMINI_SYSTEM_MD"] = temp_prompt_path
    
    # Launch gemini in interactive mode (-i) with the initial directive
    cmd = ["gemini", "-i", initial_directive]
    
    try:
        subprocess.run(cmd, env=env, check=False)
    except FileNotFoundError:
        print("Error: 'gemini' CLI not found. Please ensure it is installed and in your PATH.")
        sys.exit(1)
    except Exception as e:
        print(f"Error launching Adjutant: {e}")
        sys.exit(1)
    finally:
        # Clean up the temporary prompt
        if os.path.exists(temp_prompt_path):
            os.remove(temp_prompt_path)
