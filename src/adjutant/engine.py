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
    # We use an absolute path to ensure it's found regardless of where the command is run
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    system_prompt_path = os.path.join(base_dir, "adjutant", "adjutant_system.md")
    
    # Configure the environment to override the system prompt
    env = os.environ.copy()
    env["GEMINI_SYSTEM_MD"] = system_prompt_path
    
    # We also want to ensure experimental agents are enabled in case they aren't in settings.json
    # Though it's better to rely on settings.json for persistence.
    
    # Launch gemini in interactive mode (-i) with the initial directive
    cmd = ["gemini", "-i", initial_directive]
    
    try:
        # We use subprocess.run without capturing output to allow 
        # the interactive gemini session to take over the terminal.
        subprocess.run(cmd, env=env, check=False)
    except FileNotFoundError:
        print("Error: 'gemini' CLI not found. Please ensure it is installed and in your PATH.")
        sys.exit(1)
    except Exception as e:
        print(f"Error launching Adjutant: {e}")
        sys.exit(1)
