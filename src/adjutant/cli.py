import argparse
from adjutant.engine import run_adjutant_agent

def main():
    parser = argparse.ArgumentParser(description="Adjutant Autonomous Development Loop")
    parser.add_argument("mission", nargs="*", help="Initial mission directive")
    args = parser.parse_args()
    
    mission_directive = " ".join(args.mission)
    if not mission_directive:
        mission_directive = "I'm ready to assist with a mission."
        
    run_adjutant_agent(mission_directive)

if __name__ == "__main__":
    main()
