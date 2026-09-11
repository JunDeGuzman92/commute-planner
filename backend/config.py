"""Feed URLs and local paths for the commute planner backend."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
GTFS_DIR = DATA_DIR / "gtfs"
GTFS_ZIP = DATA_DIR / "drt_gtfs.zip"
DB_PATH = DATA_DIR / "transit.db"

GTFS_STATIC_URL = "https://maps.durham.ca/OpenDataGTFS/GTFS_Durham_TXT.zip"
GTFS_RT_VEHICLE_POSITIONS = "https://drtonline.durhamregiontransit.com/gtfsrealtime/VehiclePositions"
GTFS_RT_TRIP_UPDATES = "https://drtonline.durhamregiontransit.com/gtfsrealtime/TripUpdates"
GTFS_RT_ALERTS = "https://maps.durham.ca/OpenDataGTFS/alerts.pb"

# Real-time polling interval (seconds)
RT_POLL_INTERVAL = 30

# Walking assumptions
WALK_SPEED_MPS = 1.4          # ~5 km/h
MAX_WALK_METERS = 1500        # max walk leg to/from a stop
TRANSFER_BUFFER_SECONDS = 120  # minimum slack when changing vehicles
