"""Poll DRT's GTFS-RT feeds and expose per-(trip, stop) delay adjustments.

The router builds its connection list from the static schedule. Before a
query runs, `apply_delays` shifts each connection's dep/arr by the live
delay for that trip at that stop, so results reflect what's actually on
the road right now.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import requests
from google.transit import gtfs_realtime_pb2

from config import (
    GTFS_RT_ALERTS,
    GTFS_RT_TRIP_UPDATES,
    GTFS_RT_VEHICLE_POSITIONS,
    RT_POLL_INTERVAL,
)


@dataclass
class VehicleInfo:
    trip_id: str
    vehicle_id: str
    lat: float
    lon: float
    timestamp: int


class RealtimeStore:
    """Thread-safe container for the latest realtime snapshot."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (trip_id, stop_id) -> predicted arrival/departure as Unix time
        self._stop_predictions: dict[tuple[str, str], int] = {}
        self._trip_delays: dict[str, int] = {}
        self._vehicles: list[VehicleInfo] = []
        self._alerts: list[str] = []
        self.last_update: float = 0.0
        self.last_error: str | None = None

    # ---------- writers ----------

    def update_trip_predictions(
        self,
        stop_predictions: dict[tuple[str, str], int],
        trip_delays: dict[str, int],
    ) -> None:
        with self._lock:
            self._stop_predictions = stop_predictions
            self._trip_delays = trip_delays
            self.last_update = time.time()

    def update_vehicles(self, vehicles: list[VehicleInfo]) -> None:
        with self._lock:
            self._vehicles = vehicles

    def update_alerts(self, alerts: list[str]) -> None:
        with self._lock:
            self._alerts = alerts

    # ---------- readers ----------

    def predicted_time(self, trip_id: str, stop_id: str) -> int | None:
        """Predicted Unix time for (trip, stop), or None if unknown."""
        with self._lock:
            return self._stop_predictions.get((trip_id, stop_id))

    def trip_delay(self, trip_id: str) -> int:
        with self._lock:
            return self._trip_delays.get(trip_id, 0)

    def current_delays(self) -> dict:
        """Snapshot of {trip_id: delay_seconds} for delay-risk scoring."""
        with self._lock:
            return dict(self._trip_delays)

    def vehicles(self) -> list[VehicleInfo]:
        with self._lock:
            return list(self._vehicles)

    def alerts(self) -> list[str]:
        with self._lock:
            return list(self._alerts)

    def status(self) -> dict:
        with self._lock:
            return {
                "last_update": self.last_update,
                "age_seconds": round(time.time() - self.last_update, 1)
                if self.last_update
                else None,
                "tracked_trips": len(self._trip_delays),
                "stop_predictions": len(self._stop_predictions),
                "vehicles": len(self._vehicles),
                "alerts": len(self._alerts),
                "last_error": self.last_error,
            }


# ---------- feed parsing ----------

def parse_trip_updates(payload: bytes) -> tuple[dict, dict]:
    """Return ({(trip_id, stop_id): predicted_unix_time}, {trip_id: delay}).

    DRT's feed publishes absolute predicted arrival/departure times (Unix
    epoch) per stop, not delay offsets. We store the predicted times and
    let `apply_delays` compute the shift against the static schedule.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)
    stop_times: dict[tuple[str, str], int] = {}
    trip_delays: dict[str, int] = {}
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip_id = tu.trip.trip_id
        if not trip_id:
            continue
        if tu.HasField("delay") and tu.delay:
            trip_delays[trip_id] = tu.delay
        for stu in tu.stop_time_update:
            ts = None
            if stu.HasField("arrival") and stu.arrival.time:
                ts = stu.arrival.time
            elif stu.HasField("departure") and stu.departure.time:
                ts = stu.departure.time
            if ts is not None and stu.stop_id:
                stop_times[(trip_id, stu.stop_id)] = ts
    return stop_times, trip_delays


def parse_vehicle_positions(payload: bytes) -> list[VehicleInfo]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)
    out: list[VehicleInfo] = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        if not (v.HasField("position") and v.trip.trip_id):
            continue
        out.append(
            VehicleInfo(
                trip_id=v.trip.trip_id,
                vehicle_id=v.vehicle.id or "",
                lat=v.position.latitude,
                lon=v.position.longitude,
                timestamp=v.timestamp,
            )
        )
    return out


def parse_alerts(payload: bytes) -> list[str]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)
    out: list[str] = []
    for entity in feed.entity:
        if not entity.HasField("alert"):
            continue
        a = entity.alert
        text = ""
        if a.header_text.translation:
            text = a.header_text.translation[0].text
        elif a.description_text.translation:
            text = a.description_text.translation[0].text
        if text:
            out.append(text)
    return out


# ---------- polling loop ----------

class RealtimePoller:
    def __init__(self, store: RealtimeStore):
        self.store = store
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _fetch(self, url: str) -> bytes | None:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return resp.content
        except requests.RequestException as exc:
            self.store.last_error = str(exc)
            return None

    def tick(self) -> None:
        """One polling cycle. Safe to call manually for tests."""
        payload = self._fetch(GTFS_RT_TRIP_UPDATES)
        if payload:
            stop_predictions, trip_delays = parse_trip_updates(payload)
            self.store.update_trip_predictions(stop_predictions, trip_delays)

        payload = self._fetch(GTFS_RT_VEHICLE_POSITIONS)
        if payload:
            self.store.update_vehicles(parse_vehicle_positions(payload))

        payload = self._fetch(GTFS_RT_ALERTS)
        if payload:
            self.store.update_alerts(parse_alerts(payload))

    def _run(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(RT_POLL_INTERVAL)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)


if __name__ == "__main__":
    store = RealtimeStore()
    poller = RealtimePoller(store)
    print("Fetching live feeds once...")
    poller.tick()
    status = store.status()
    for k, v in status.items():
        print(f"  {k}: {v}")
    for veh in store.vehicles()[:3]:
        print(f"  vehicle {veh.vehicle_id}: trip {veh.trip_id} "
              f"@ ({veh.lat:.5f}, {veh.lon:.5f})")
    # sample a prediction and compute its live delay vs static schedule
    import sqlite3
    from datetime import datetime
    from config import DB_PATH
    sample = None
    with store._lock:
        for k in list(store._stop_predictions.keys())[:200]:
            sample = k
            break
    if sample:
        trip_id, stop_id = sample
        pred = store.predicted_time(trip_id, stop_id)
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT arrival_time FROM stop_times WHERE trip_id=? AND stop_id=?",
            (trip_id, stop_id),
        ).fetchone()
        conn.close()
        if row:
            h, m, s = row[0].split(":")
            sched_s = int(h) * 3600 + int(m) * 60 + int(s)
            # service day midnight as unix
            today_midnight = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0).timestamp()
            sched_unix = int(today_midnight) + sched_s
            print(f"  sample trip {trip_id} stop {stop_id}: "
                  f"scheduled={row[0]} predicted={datetime.fromtimestamp(pred).strftime('%H:%M:%S')} "
                  f"delay={pred - sched_unix:+d}s")
