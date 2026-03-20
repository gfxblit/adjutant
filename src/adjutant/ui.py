import time
from adjutant.engine import AdjutantHUD

def run_ui(mission: str):
    """
    Runs the Adjutant HUD in the main thread until interrupted.
    """
    print(f"[Adjutant HUD: Monitoring Mission: {mission}]")
    print("Press Ctrl+C to exit.")
    
    hud = AdjutantHUD(mission=mission)
    hud.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Adjutant HUD: Shutting Down]")
    finally:
        hud.stop()
