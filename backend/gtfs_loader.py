"""Download, parse, and load the DRT static GTFS feed into SQLite.

DRT's feed uses a nonstandard column order in several files, so every
table is read with pandas (header-driven) rather than by position.
"""
from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path

import pandas as pd
import requests

from config import DB_PATH, GTFS_DIR, GTFS_STATIC_URL, GTFS_ZIP

GTFS_TABLES = [
    "agency",
    "calendar",
    "calendar_dates",
    "routes",
    "trips",
    "stops",
    "stop_times",
    "shapes",
    "fare_attributes",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS stops (
    stop_id TEXT PRIMARY KEY,
    stop_code TEXT,
    stop_name TEXT,
    stop_lat REAL,
    stop_lon REAL,
    location_type INTEGER,
    parent_station TEXT,
    wheelchair_boarding INTEGER
);

CREATE TABLE IF NOT EXISTS routes (
    route_id TEXT PRIMARY KEY,
    route_short_name TEXT,
    route_long_name TEXT,
    route_type INTEGER,
    route_color TEXT,
    route_text_color TEXT
);

CREATE TABLE IF NOT EXISTS trips (
    trip_id TEXT PRIMARY KEY,
    route_id TEXT,
    service_id TEXT,
    trip_headsign TEXT,
    direction_id INTEGER,
    block_id TEXT,
    shape_id TEXT
);

CREATE TABLE IF NOT EXISTS stop_times (
    trip_id TEXT,
    arrival_time TEXT,
    departure_time TEXT,
    stop_id TEXT,
    stop_sequence INTEGER,
    pickup_type INTEGER,
    drop_off_type INTEGER
);

CREATE TABLE IF NOT EXISTS calendar (
    service_id TEXT PRIMARY KEY,
    monday INTEGER, tuesday INTEGER, wednesday INTEGER,
    thursday INTEGER, friday INTEGER, saturday INTEGER, sunday INTEGER,
    start_date TEXT, end_date TEXT
);

CREATE TABLE IF NOT EXISTS calendar_dates (
    service_id TEXT,
    date TEXT,
    exception_type INTEGER
);

CREATE TABLE IF NOT EXISTS shapes (
    shape_id TEXT,
    shape_pt_lat REAL,
    shape_pt_lon REAL,
    shape_pt_sequence INTEGER,
    shape_dist_traveled REAL
);

CREATE INDEX IF NOT EXISTS idx_stop_times_trip ON stop_times(trip_id, stop_sequence);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop ON stop_times(stop_id, departure_time);
CREATE INDEX IF NOT EXISTS idx_trips_route ON trips(route_id);
CREATE INDEX IF NOT EXISTS idx_trips_service ON trips(service_id);
"""


def download_gtfs(url: str = GTFS_STATIC_URL, dest: Path = GTFS_ZIP) -> Path:
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def extract_gtfs(zip_path: Path = GTFS_ZIP, dest: Path = GTFS_DIR) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    return dest


def _read_gtfs_table(name: str, gtfs_dir: Path) -> pd.DataFrame | None:
    path = gtfs_dir / f"{name}.txt"
    if not path.exists() or path.stat().st_size == 0:
        return None
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_into_sqlite(gtfs_dir: Path = GTFS_DIR, db_path: Path = DB_PATH) -> dict:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        stats: dict[str, int] = {}

        stops = _read_gtfs_table("stops", gtfs_dir)
        if stops is not None:
            stops[[
                "stop_id", "stop_code", "stop_name", "stop_lat", "stop_lon",
                "location_type", "parent_station", "wheelchair_boarding",
            ]].to_sql("stops", conn, if_exists="append", index=False)
            stats["stops"] = len(stops)

        routes = _read_gtfs_table("routes", gtfs_dir)
        if routes is not None:
            routes[[
                "route_id", "route_short_name", "route_long_name",
                "route_type", "route_color", "route_text_color",
            ]].to_sql("routes", conn, if_exists="append", index=False)
            stats["routes"] = len(routes)

        trips = _read_gtfs_table("trips", gtfs_dir)
        if trips is not None:
            trips[[
                "trip_id", "route_id", "service_id", "trip_headsign",
                "direction_id", "block_id", "shape_id",
            ]].to_sql("trips", conn, if_exists="append", index=False)
            stats["trips"] = len(trips)

        stop_times = _read_gtfs_table("stop_times", gtfs_dir)
        if stop_times is not None:
            stop_times["stop_sequence"] = stop_times["stop_sequence"].astype(int)
            for col in ("pickup_type", "drop_off_type"):
                if col not in stop_times.columns:
                    stop_times[col] = "0"
                stop_times[col] = stop_times[col].replace("", "0").astype(int)
            stop_times[[
                "trip_id", "arrival_time", "departure_time",
                "stop_id", "stop_sequence", "pickup_type", "drop_off_type",
            ]].to_sql("stop_times", conn, if_exists="append", index=False)
            stats["stop_times"] = len(stop_times)

        calendar = _read_gtfs_table("calendar", gtfs_dir)
        if calendar is not None:
            calendar[[
                "service_id", "monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday", "start_date", "end_date",
            ]].to_sql("calendar", conn, if_exists="append", index=False)
            stats["calendar"] = len(calendar)

        cal_dates = _read_gtfs_table("calendar_dates", gtfs_dir)
        if cal_dates is not None and len(cal_dates):
            cal_dates[["service_id", "date", "exception_type"]].to_sql(
                "calendar_dates", conn, if_exists="append", index=False
            )
            stats["calendar_dates"] = len(cal_dates)

        shapes = _read_gtfs_table("shapes", gtfs_dir)
        if shapes is not None:
            keep = [c for c in (
                "shape_id", "shape_pt_lat", "shape_pt_lon",
                "shape_pt_sequence", "shape_dist_traveled",
            ) if c in shapes.columns]
            shapes[keep].to_sql("shapes", conn, if_exists="append", index=False)
            stats["shapes"] = len(shapes)

        conn.commit()
    finally:
        conn.close()
    return stats


def validate(db_path: Path = DB_PATH) -> list[str]:
    """Sanity checks that catch a broken feed before the router ever sees it."""
    problems: list[str] = []
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        orphan_times = cur.execute(
            "SELECT COUNT(*) FROM stop_times st LEFT JOIN stops s "
            "ON st.stop_id = s.stop_id WHERE s.stop_id IS NULL"
        ).fetchone()[0]
        if orphan_times:
            problems.append(f"{orphan_times} stop_times reference missing stops")

        orphan_trips = cur.execute(
            "SELECT COUNT(*) FROM stop_times st LEFT JOIN trips t "
            "ON st.trip_id = t.trip_id WHERE t.trip_id IS NULL"
        ).fetchone()[0]
        if orphan_trips:
            problems.append(f"{orphan_trips} stop_times reference missing trips")

        no_times = cur.execute(
            "SELECT COUNT(*) FROM trips t WHERE NOT EXISTS "
            "(SELECT 1 FROM stop_times st WHERE st.trip_id = t.trip_id)"
        ).fetchone()[0]
        if no_times:
            problems.append(f"{no_times} trips have no stop_times")

        bad_coords = cur.execute(
            "SELECT COUNT(*) FROM stops WHERE stop_lat IS NULL OR stop_lon IS NULL "
            "OR stop_lat = 0 OR stop_lon = 0"
        ).fetchone()[0]
        if bad_coords:
            problems.append(f"{bad_coords} stops have bad coordinates")
    finally:
        conn.close()
    return problems


def main() -> None:
    print("Downloading GTFS...")
    download_gtfs()
    print("Extracting...")
    extract_gtfs()
    print("Loading into SQLite...")
    stats = load_into_sqlite()
    for table, count in stats.items():
        print(f"  {table}: {count:,} rows")
    print("Validating...")
    problems = validate()
    if problems:
        for p in problems:
            print(f"  WARNING: {p}")
    else:
        print("  all checks passed")
    print("Done.")


if __name__ == "__main__":
    main()
