import argparse
from adjutant.engine import run_base_loop

def main():
    parser = argparse.ArgumentParser(description="Adjutant Autonomous Development Loop")
    parser.add_argument("--mission", help="Specific mission ID to execute", default=None)
    args = parser.parse_args()
    
    run_base_loop(mission_id=args.mission)

if __name__ == "__main__":
    main()
