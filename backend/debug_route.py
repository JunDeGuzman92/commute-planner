from datetime import date
from router import TransitRouter, _hhmm_to_seconds, format_gtfs_time

r = TransitRouter()
r.load_service_day(date(2026, 9, 10))

# The exact failing API query
opts = r.route(43.87593224, -78.961715, 43.87268331, -78.855412,
               _hhmm_to_seconds("16:30"))
for opt in opts:
    print(f"option: {format_gtfs_time(opt.depart)}->{format_gtfs_time(opt.arrive)}")
    for leg in opt.legs:
        print(f"  {leg.mode} R{leg.route_name} {leg.from_name} -> {leg.to_name}")
        print(f"     depart={format_gtfs_time(leg.depart)} "
              f"arrive={format_gtfs_time(leg.arrive)} stops={leg.num_stops}")

# Inspect trip 306's connection sequence around 16:45 to see ordering
import sqlite3
conn = sqlite3.connect(r.db_path)
print("\n=== 306 trips departing 16:40-16:50 near origin ===")
rows = conn.execute(
    """
    SELECT st.trip_id, st.stop_id, s.stop_name, st.departure_time, st.stop_sequence
    FROM stop_times st JOIN trips t ON t.trip_id=st.trip_id
    JOIN stops s ON s.stop_id=st.stop_id
    WHERE t.route_id='306' AND st.departure_time BETWEEN '16:44' AND '16:50'
    ORDER BY st.trip_id, st.stop_sequence
    LIMIT 12
    """
).fetchall()
for x in rows:
    print(x)
conn.close()
