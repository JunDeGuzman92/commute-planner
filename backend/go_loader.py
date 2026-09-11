"""Download and merge GO Transit GTFS into the shared transit database.

GO's feed uses standard GTFS layout (unlike DRT's reordered columns).
All IDs are prefixed with 'GO:' so the two agencies share one connection
graph without collisions. After merge, we build walk-transfer edges between
DRT stops and GO stations within WALK_TRANSFER_M of each other — that's
what lets the router produce DRT->GO journeys.

Metrolinx Access and Use Agreement requires the attribution legend shown
in the frontend footer and README.

Schema matches gtfs_loader.py:
  stops(stop_id, stop_code, stop_name, stop_lat, stop_lon,
        location_type, parent_station, wheelchair_boarding)
  routes(route_id, route_short_name, route_long_name, route_type,
         route_color, route_text_color)
  trips(trip_id, route_id, service_id, trip_headsign, direction_id,
        block_id, shape_id)
  stop_times(trip_id, arrival_time, departure_time, stop_id,
             stop_sequence, pickup_type, drop_off_type)
  calendar(service_id, mon..sun, start_date, end_date)
  calendar_dates(service_id, date, exception_type)
  shapes(shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence,
         shape_dist_traveled)
"""
from __future__ import annotations

import csv
import io
import sqlite3
import zipfile

import requests

from config import DB_PATH, DATA_DIR
from router import haversine_m

GO_GTFS_URL = ("https://assets.metrolinx.com/raw/upload/Documents/"
               "Metrolinx/Open%20Data/GO-GTFS.zip")
GO_ZIP = DATA_DIR / "go_gtfs.zip"
GO_PREFIX = "GO:"
WALK_TRANSFER_M = 400  # max stop->station walk for a transfer edge


def download_go_gtfs() -> None:
    print("Downloading GO GTFS...")
    resp = requests.get(GO_GTFS_URL, timeout=300)
    resp.raise_for_status()
    GO_ZIP.write_bytes(resp.content)
    print(f"  {len(resp.content) / 1e6:.1f} MB")


def _read_gtfs_table(zf: zipfile.ZipFile, name: str) -> list[dict]:
    with zf.open(name) as f:
        text = io.TextIOWrapper(f, encoding="utf-8-sig")
        return list(csv.DictReader(text))


def merge_go_gtfs() -> dict:
    """Merge GO data into transit.db alongside DRT tables."""
    if not GO_ZIP.exists():
        download_go_gtfs()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Clean any previous GO merge so re-runs are idempotent
    cur.execute("DELETE FROM stops WHERE stop_id LIKE 'GO:%'")
    cur.execute("DELETE FROM routes WHERE route_id LIKE 'GO:%'")
    cur.execute("DELETE FROM trips WHERE trip_id LIKE 'GO:%'")
    cur.execute("DELETE FROM stop_times WHERE trip_id LIKE 'GO:%'")
    cur.execute("DELETE FROM calendar WHERE service_id LIKE 'GO:%'")
    cur.execute("DELETE FROM calendar_dates WHERE service_id LIKE 'GO:%'")
    cur.execute("DELETE FROM shapes WHERE shape_id LIKE 'GO:%'")

    stats = {}
    with zipfile.ZipFile(GO_ZIP) as zf:
        names = set(zf.namelist())

        rows = _read_gtfs_table(zf, "stops.txt")
        for r in rows:
            cur.execute(
                "INSERT OR REPLACE INTO stops VALUES (?,?,?,?,?,?,?,?)",
                (GO_PREFIX + r["stop_id"], r.get("stop_code", ""),
                 r.get("stop_name", ""), float(r["stop_lat"]),
                 float(r["stop_lon"]),
                 int(r.get("location_type") or 0),
                 (GO_PREFIX + r["parent_station"])
                 if r.get("parent_station") else None,
                 int(r.get("wheelchair_boarding") or 0)),
            )
        stats["stops"] = len(rows)

        rows = _read_gtfs_table(zf, "routes.txt")
        for r in rows:
            cur.execute(
                "INSERT OR REPLACE INTO routes VALUES (?,?,?,?,?,?)",
                (GO_PREFIX + r["route_id"], r.get("route_short_name", ""),
                 r.get("route_long_name", ""),
                 int(r.get("route_type") or 3),
                 r.get("route_color", ""), r.get("route_text_color", "")),
            )
        stats["routes"] = len(rows)

        # GO publishes calendar_dates only (no weekly calendar.txt).
        # Synthesize a calendar row per service_id spanning the feed's
        # date range, with all weekdays on — calendar_dates then act as
        # add/remove exceptions, which load_service_day already handles.
        if "calendar_dates.txt" in names:
            rows = _read_gtfs_table(zf, "calendar_dates.txt")
            by_service: dict[str, list[str]] = {}
            for r in rows:
                cur.execute(
                    "INSERT OR REPLACE INTO calendar_dates VALUES (?,?,?)",
                    (GO_PREFIX + r["service_id"], r["date"],
                     int(r["exception_type"])),
                )
                by_service.setdefault(r["service_id"], []).append(r["date"])
            stats["calendar_dates"] = len(rows)

            for sid, dates in by_service.items():
                # All weekdays OFF: service runs only on its explicit
                # calendar_dates (exception_type=1 additions).
                cur.execute(
                    "INSERT OR REPLACE INTO calendar VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (GO_PREFIX + sid, 0, 0, 0, 0, 0, 0, 0,
                     min(dates), max(dates)),
                )
            stats["calendar"] = len(by_service)
        else:
            stats["calendar_dates"] = 0
            stats["calendar"] = 0

        rows = _read_gtfs_table(zf, "trips.txt")
        for r in rows:
            cur.execute(
                "INSERT OR REPLACE INTO trips VALUES (?,?,?,?,?,?,?)",
                (GO_PREFIX + r["trip_id"], GO_PREFIX + r["route_id"],
                 GO_PREFIX + r["service_id"], r.get("trip_headsign", ""),
                 int(r.get("direction_id") or 0), r.get("block_id"),
                 (GO_PREFIX + r["shape_id"]) if r.get("shape_id") else None),
            )
        stats["trips"] = len(rows)

        rows = _read_gtfs_table(zf, "stop_times.txt")
        for r in rows:
            cur.execute(
                "INSERT OR REPLACE INTO stop_times VALUES (?,?,?,?,?,?,?)",
                (GO_PREFIX + r["trip_id"], r["arrival_time"],
                 r["departure_time"], GO_PREFIX + r["stop_id"],
                 int(r["stop_sequence"]),
                 int(r.get("pickup_type") or 0),
                 int(r.get("drop_off_type") or 0)),
            )
        stats["stop_times"] = len(rows)

        if "shapes.txt" in names:
            rows = _read_gtfs_table(zf, "shapes.txt")
            for r in rows:
                cur.execute(
                    "INSERT OR REPLACE INTO shapes VALUES (?,?,?,?,?)",
                    (GO_PREFIX + r["shape_id"], float(r["shape_pt_lat"]),
                     float(r["shape_pt_lon"]), int(r["shape_pt_sequence"]),
                     float(r.get("shape_dist_traveled") or 0)),
                )
            stats["shapes"] = len(rows)
        else:
            stats["shapes"] = 0

    conn.commit()

    # --- walk-transfer edges between DRT stops and GO stations ---
    cur.execute("SELECT stop_id, stop_lat, stop_lon FROM stops "
                "WHERE stop_id LIKE 'GO:%' AND location_type = 0")
    go_stops = cur.fetchall()
    cur.execute("SELECT stop_id, stop_lat, stop_lon FROM stops "
                "WHERE stop_id NOT LIKE 'GO:%'")
    drt_stops = cur.fetchall()

    cur.execute("""CREATE TABLE IF NOT EXISTS transfer_edges (
        from_stop TEXT, to_stop TEXT, walk_m REAL,
        PRIMARY KEY (from_stop, to_stop))""")
    cur.execute("DELETE FROM transfer_edges WHERE from_stop LIKE 'GO:%' "
                "OR to_stop LIKE 'GO:%'")

    edges = 0
    for go_id, go_lat, go_lon in go_stops:
        for drt_id, drt_lat, drt_lon in drt_stops:
            d = haversine_m(go_lat, go_lon, drt_lat, drt_lon)
            if d <= WALK_TRANSFER_M:
                cur.execute(
                    "INSERT OR REPLACE INTO transfer_edges VALUES (?,?,?)",
                    (drt_id, go_id, round(d)))
                cur.execute(
                    "INSERT OR REPLACE INTO transfer_edges VALUES (?,?,?)",
                    (go_id, drt_id, round(d)))
                edges += 2
    conn.commit()
    stats["transfer_edges"] = edges
    conn.close()
    return stats


if __name__ == "__main__":
    print(merge_go_gtfs())
