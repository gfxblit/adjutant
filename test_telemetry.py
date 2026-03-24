import sys
import os

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from adjutant.hooks import get_mission_telemetry

print(get_mission_telemetry())
