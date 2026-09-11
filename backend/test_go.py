"""Verify GO merge + test a cross-agency route."""
import sqlite3
from datetime import date

conn = sqlite3.connect(r"C:\Users\junbu\Documents\commute-planner\data\transit.db")
conn.row_factory = sqlite3.Row

# What's active today (Friday 2026-09-11)?
today = "20260911"
svcs = conn.execute(
    "SELECT service_id FROM calendar_dates WHERE date=? AND exception_type=1 "
    "AND service_id LIKE 'GO:%'", (today,)).fetchall()
print(f"GO services active today: {len(svcs)}")

trips = conn.execute(
    "SELECT COUNT(*) c FROM trips WHERE service_id IN "
    f"({','.join('?'*len(svcs))})",
    tuple(s['service_id'] for s in svcs)).fetchone()
print(f"GO trips today: {trips['c']}")

# Sample a Lakeshore East trip
le = conn.execute(
    "SELECT t.trip_id, t.trip_headsign, r.route_short_name "
    "FROM trips t JOIN routes r ON r.route_id=t.route_id "
    "WHERE t.service_id IN (" + ",".join("?"*len(svcs)) + ") "
    "AND r.route_long_name LIKE '%Lakeshore East%' LIMIT 5",
    tuple(s['service_id'] for s in svcs)).fetchall()
for t in le:
    print(f"  {t['trip_id']} -> {t['trip_headsign']}")

# Transfer edges sample
edges = conn.execute(
    "SELECT COUNT(*) c FROM transfer_edges").fetchone()
print(f"Transfer edges: {edges['c']}")

# GO station names near Whitby
st = conn.execute(
    "SELECT stop_id, stop_name FROM stops WHERE stop_name LIKE '%Whitby%' "
    "AND stop_id LIKE 'GO:%'").fetchall()
for s in st:
    print(f"  {s['stop_id']}: {s['stop_name']}")
conn.close()
