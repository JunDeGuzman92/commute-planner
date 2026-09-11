"""Time-dependent multi-criteria router over the DRT GTFS network.

Approach: expanded Connection Scan Algorithm with Pareto labels.
Each label at a stop tracks (arrival_time, transfers, walk_m) and we keep
the Pareto-optimal set per stop, so a query returns a frontier of routes
instead of a single "best" one: fastest, fewest transfers, least walking.

GTFS times are HH:MM:SS and may exceed 24:00:00 for after-midnight trips,
so all internal times are seconds-since-service-day-midnight.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from config import DB_PATH, TRANSFER_BUFFER_SECONDS, WALK_SPEED_MPS

EARTH_RADIUS_M = 6_371_000


def parse_gtfs_time(t: str) -> int:
    """'25:14:00' -> seconds since service-day midnight."""
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def format_gtfs_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h:02d}:{m:02d}"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Connection:
    trip_id: str
    route_id: str
    from_stop: str
    to_stop: str
    dep: int
    arr: int


@dataclass
class Label:
    """One Pareto candidate for reaching a stop.

    Carries its own path: `legs` is the tuple of completed transit legs,
    and the `open_*` fields describe the ride currently in progress (if
    any). This avoids fragile parent-pointer reconstruction.
    """
    arrival: int
    transfers: int
    walk_m: float
    stop_id: str
    legs: tuple = ()            # tuple[RouteLeg], completed transit legs
    # open ride state (the vehicle currently being ridden)
    open_trip: str | None = None
    open_route: str | None = None
    open_board_stop: str | None = None
    open_board_time: int | None = None
    open_stops_ridden: int = 0

    def dominates(self, other: "Label") -> bool:
        a = (self.arrival, self.transfers, round(self.walk_m))
        b = (other.arrival, other.transfers, round(other.walk_m))
        return a <= b and a != b


@dataclass
class RouteLeg:
    mode: str               # "walk" or "transit"
    from_stop: str
    to_stop: str
    from_name: str
    to_name: str
    depart: int
    arrive: int
    route_id: str | None = None
    route_name: str | None = None
    headsign: str | None = None
    num_stops: int = 0
    distance_m: float = 0.0
    trip_id: str | None = None  # needed for shape lookup


@dataclass
class RouteOption:
    legs: list[RouteLeg]
    depart: int
    arrive: int
    transfers: int
    walk_m: float

    @property
    def duration_s(self) -> int:
        return self.arrive - self.depart


class TransitRouter:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.stops: dict[str, dict] = {}
        self.stop_coords: dict[str, tuple[float, float]] = {}
        self.connections: list[Connection] = []
        self.trip_route: dict[str, str] = {}
        self.trip_headsign: dict[str, str] = {}
        self.trip_stop_sequence: dict[str, list[str]] = {}
        self.trip_shape: dict[str, str] = {}  # trip_id -> shape_id
        self.shapes: dict[str, list[tuple[float, float]]] = {}  # shape_id -> [(lat, lon), ...]
        self.route_names: dict[str, str] = {}
        self._load_static()

    # ---------- loading ----------

    def _load_static(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            for r in conn.execute(
                "SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops"
            ):
                self.stops[r["stop_id"]] = dict(r)
                self.stop_coords[r["stop_id"]] = (r["stop_lat"], r["stop_lon"])

            for r in conn.execute(
                "SELECT route_id, route_short_name, route_long_name FROM routes"
            ):
                name = r["route_short_name"] or r["route_long_name"] or r["route_id"]
                self.route_names[r["route_id"]] = name

            for r in conn.execute(
                "SELECT trip_id, route_id, trip_headsign, shape_id FROM trips"
            ):
                self.trip_route[r["trip_id"]] = r["route_id"]
                self.trip_headsign[r["trip_id"]] = r["trip_headsign"] or ""
                if r["shape_id"]:
                    self.trip_shape[r["trip_id"]] = r["shape_id"]

            # Load shapes for geometry rendering
            shape_pts: dict[str, list[tuple[int, float, float]]] = {}
            for r in conn.execute(
                "SELECT shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence "
                "FROM shapes ORDER BY shape_id, shape_pt_sequence"
            ):
                shape_pts.setdefault(r["shape_id"], []).append(
                    (r["shape_pt_sequence"], r["shape_pt_lat"], r["shape_pt_lon"])
                )
            self.shapes = {
                sid: [(lat, lon) for _, lat, lon in sorted(pts)]
                for sid, pts in shape_pts.items()
            }

            seq: dict[str, list[tuple[int, str]]] = {}
            for r in conn.execute(
                "SELECT trip_id, stop_id, stop_sequence FROM stop_times "
                "ORDER BY trip_id, stop_sequence"
            ):
                seq.setdefault(r["trip_id"], []).append(
                    (r["stop_sequence"], r["stop_id"])
                )
            self.trip_stop_sequence = {
                t: [s for _, s in sorted(v)] for t, v in seq.items()
            }
        finally:
            conn.close()

    def load_service_day(self, service_date: date) -> int:
        """Materialize connections for one service date. Returns count."""
        yyyymmdd = service_date.strftime("%Y%m%d")
        weekday = service_date.strftime("%A").lower()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            service_ids = {
                row["service_id"]
                for row in conn.execute(
                    f"SELECT service_id FROM calendar "
                    f"WHERE {weekday} = 1 AND start_date <= ? AND end_date >= ?",
                    (yyyymmdd, yyyymmdd),
                )
            }
            for row in conn.execute(
                "SELECT service_id, exception_type FROM calendar_dates WHERE date = ?",
                (yyyymmdd,),
            ):
                if row["exception_type"] == 1:
                    service_ids.add(row["service_id"])
                elif row["exception_type"] == 2:
                    service_ids.discard(row["service_id"])

            if not service_ids:
                self.connections = []
                return 0

            placeholders = ",".join("?" * len(service_ids))
            rows = conn.execute(
                f"""
                SELECT st.trip_id, st.stop_id, st.stop_sequence,
                       st.departure_time, st.arrival_time, t.route_id
                FROM stop_times st
                JOIN trips t ON t.trip_id = st.trip_id
                WHERE t.service_id IN ({placeholders})
                ORDER BY st.trip_id, st.stop_sequence
                """,
                tuple(service_ids),
            ).fetchall()
        finally:
            conn.close()

        conns: list[Connection] = []
        prev_trip: str | None = None
        prev_stop: str | None = None
        prev_dep: int | None = None
        for r in rows:
            trip = r["trip_id"]
            dep = parse_gtfs_time(r["departure_time"])
            arr = parse_gtfs_time(r["arrival_time"])
            if (
                prev_trip == trip
                and prev_stop is not None
                and prev_dep is not None
                and dep >= prev_dep
            ):
                conns.append(
                    Connection(trip, r["route_id"], prev_stop, r["stop_id"],
                               prev_dep, arr)
                )
            prev_trip, prev_stop, prev_dep = trip, r["stop_id"], dep

        conns.sort(key=lambda c: c.dep)
        self.connections = conns
        return len(conns)

    # ---------- realtime ----------

    def apply_realtime(self, rt_store, service_date: date) -> list[Connection]:
        """Return a copy of connections with live delays applied.

        For each connection, if the realtime store has a predicted Unix time
        for (trip, from_stop), we shift dep/arr by (predicted - scheduled).
        Falls back to trip-level delay, then to the static schedule.
        """
        midnight_unix = int(datetime(
            service_date.year, service_date.month, service_date.day
        ).timestamp())
        adjusted: list[Connection] = []
        for c in self.connections:
            shift = 0
            pred = rt_store.predicted_time(c.trip_id, c.from_stop)
            if pred is not None:
                shift = pred - (midnight_unix + c.dep)
            else:
                shift = rt_store.trip_delay(c.trip_id)
            if shift:
                adjusted.append(Connection(
                    c.trip_id, c.route_id, c.from_stop, c.to_stop,
                    c.dep + shift, c.arr + shift,
                ))
            else:
                adjusted.append(c)
        adjusted.sort(key=lambda c: c.dep)
        return adjusted

    # ---------- geo helpers ----------

    def nearest_stops(self, lat: float, lon: float, max_m: float, limit: int = 8):
        cand = []
        for sid, (slat, slon) in self.stop_coords.items():
            d = haversine_m(lat, lon, slat, slon)
            if d <= max_m:
                cand.append((sid, d))
        cand.sort(key=lambda x: x[1])
        return cand[:limit]

    # ---------- Pareto set ----------

    @staticmethod
    def _pareto_insert(labels: list[Label], cand: Label) -> bool:
        for existing in labels:
            if existing.dominates(cand):
                return False
        labels[:] = [l for l in labels if not cand.dominates(l)]
        labels.append(cand)
        return True

    # ---------- the scan ----------

    def route(
        self,
        from_lat: float,
        from_lon: float,
        to_lat: float,
        to_lon: float,
        depart_after: int,
        max_walk_m: float = 1200,
        max_results: int = 5,
        rt_store=None,
        service_date: date | None = None,
    ) -> list[RouteOption]:
        origin = self.nearest_stops(from_lat, from_lon, max_walk_m)
        dest_candidates = self.nearest_stops(to_lat, to_lon, max_walk_m)
        if not origin or not dest_candidates:
            return []
        dest_walk = {sid: d for sid, d in dest_candidates}

        connections = self.connections
        if rt_store is not None and service_date is not None:
            connections = self.apply_realtime(rt_store, service_date)

        labels: dict[str, list[Label]] = {}
        for sid, walk_d in origin:
            walk_s = int(walk_d / WALK_SPEED_MPS)
            self._pareto_insert(
                labels.setdefault(sid, []),
                Label(
                    arrival=depart_after + walk_s,
                    transfers=0,
                    walk_m=walk_d,
                    stop_id=sid,
                ),
            )

        # Trips currently being ridden: trip -> list of in-vehicle labels,
        # one per non-dominated boarding. Each label advances stop-by-stop
        # as the scan walks the trip's connections in departure order.
        boarded: dict[str, list[Label]] = {}
        best_final: list[Label] = []
        earliest_final = math.inf

        for conn in connections:
            if conn.dep > earliest_final:
                break

            riding: list[Label] = []
            if conn.trip_id in boarded:
                # Already riding: advance the in-vehicle labels.
                riding = boarded[conn.trip_id]
            else:
                # Try to board here: any label at this stop arriving in time.
                # Buffer applies only when transferring between vehicles.
                for lbl in labels.get(conn.from_stop, []):
                    buffer = TRANSFER_BUFFER_SECONDS if lbl.open_trip else 0
                    if lbl.arrival + buffer <= conn.dep:
                        riding.append(lbl)
                if not riding:
                    continue

            new_riding: list[Label] = []
            for base in riding:
                continuing = base.open_trip == conn.trip_id
                if continuing:
                    legs = base.legs
                    board_stop = base.open_board_stop
                    board_time = base.open_board_time
                    stops_ridden = base.open_stops_ridden + 1
                    transfers = base.transfers
                else:
                    # Boarding a different vehicle: close the previous ride
                    # (if any) into legs, then open a new one at this stop.
                    legs = base.legs
                    if base.open_trip is not None:
                        legs = legs + (self._close_leg(base),)
                    board_stop = conn.from_stop
                    board_time = conn.dep
                    stops_ridden = 1
                    transfers = base.transfers + (1 if base.open_trip else 0)
                cand = Label(
                    arrival=conn.arr,
                    transfers=transfers,
                    walk_m=base.walk_m,
                    stop_id=conn.to_stop,
                    legs=legs,
                    open_trip=conn.trip_id,
                    open_route=conn.route_id,
                    open_board_stop=board_stop,
                    open_board_time=board_time,
                    open_stops_ridden=stops_ridden,
                )
                # Carry the ride forward regardless of Pareto outcome here:
                # a label dominated at this stop may become optimal later.
                new_riding.append(cand)
                if not self._pareto_insert(labels.setdefault(conn.to_stop, []), cand):
                    pass

                if conn.to_stop in dest_walk:
                    final_walk = dest_walk[conn.to_stop]
                    final_walk_s = int(final_walk / WALK_SPEED_MPS)
                    final = Label(
                        arrival=cand.arrival + final_walk_s,
                        transfers=cand.transfers,
                        walk_m=cand.walk_m + final_walk,
                        stop_id=conn.to_stop,
                        legs=cand.legs,
                        open_trip=cand.open_trip,
                        open_route=cand.open_route,
                        open_board_stop=cand.open_board_stop,
                        open_board_time=cand.open_board_time,
                        open_stops_ridden=cand.open_stops_ridden,
                    )
                    self._pareto_insert(best_final, final)
                    if final.arrival < earliest_final:
                        earliest_final = final.arrival

            boarded[conn.trip_id] = new_riding

        best_final.sort(key=lambda l: (l.arrival, l.transfers, l.walk_m))
        return [
            self._reconstruct(lbl, depart_after, to_lat, to_lon)
            for lbl in best_final[:max_results]
        ]

    def get_leg_geometry(self, trip_id: str, from_stop: str, to_stop: str) -> dict | None:
        """Return GeoJSON geometry for a transit leg, sliced between stops.

        Uses shape_dist_traveled when available for precision, falls back to
        stop-sequence proportional slicing, then to the full shape.
        """
        shape_id = self.trip_shape.get(trip_id)
        if not shape_id:
            return None
        shape = self.shapes.get(shape_id)
        if not shape:
            return None

        # Get stop coordinates and their positions in the trip
        from_coord = self.stop_coords.get(from_stop)
        to_coord = self.stop_coords.get(to_stop)
        if not from_coord or not to_coord:
            return {"type": "LineString", "coordinates": [[c[1], c[0]] for c in shape]}

        # Find nearest shape points to the stops (project stops onto shape)
        def nearest_shape_idx(stop_lat, stop_lon):
            best_idx, best_dist = 0, float("inf")
            for i, (lat, lon) in enumerate(shape):
                d = (lat - stop_lat) ** 2 + (lon - stop_lon) ** 2
                if d < best_dist:
                    best_dist, best_idx = d, i
            return best_idx

        from_idx = nearest_shape_idx(*from_coord)
        to_idx = nearest_shape_idx(*to_coord)

        # Ensure correct order (shape may run either direction)
        if from_idx > to_idx:
            from_idx, to_idx = to_idx, from_idx

        # Slice with small buffer for smooth rendering
        buffer = 2
        start = max(0, from_idx - buffer)
        end = min(len(shape), to_idx + buffer + 1)
        sliced = shape[start:end]

        return {
            "type": "LineString",
            "coordinates": [[lon, lat] for lat, lon in sliced],
        }

    # ---------- reconstruction ----------

    def _close_leg(self, label: Label) -> RouteLeg:
        """Convert a label's completed open ride into a RouteLeg."""
        board_stop = label.open_board_stop or label.stop_id
        alight_stop = label.stop_id
        trip = label.open_trip or ""
        return RouteLeg(
            mode="transit",
            from_stop=board_stop,
            to_stop=alight_stop,
            from_name=self.stops.get(board_stop, {}).get("stop_name", board_stop),
            to_name=self.stops.get(alight_stop, {}).get("stop_name", alight_stop),
            depart=label.open_board_time or label.arrival,
            arrive=label.arrival,
            route_id=label.open_route,
            route_name=self.route_names.get(label.open_route or "",
                                            label.open_route),
            headsign=self.trip_headsign.get(trip, ""),
            num_stops=label.open_stops_ridden,
            trip_id=trip,
        )

    def _reconstruct(
        self, final: Label, query_depart: int, to_lat: float, to_lon: float
    ) -> RouteOption:
        # Close the ride that delivered us to the destination stop, then
        # append the final walk leg.
        legs: list[RouteLeg] = list(final.legs)
        if final.open_trip is not None:
            legs.append(self._close_leg(final))

        if final.stop_id in self.stop_coords:
            slat, slon = self.stop_coords[final.stop_id]
            dist = haversine_m(slat, slon, to_lat, to_lon)
            if dist > 1:
                last_arrive = legs[-1].arrive if legs else query_depart
                legs.append(RouteLeg(
                    mode="walk",
                    from_stop=final.stop_id,
                    to_stop="destination",
                    from_name=self.stops.get(final.stop_id, {}).get(
                        "stop_name", final.stop_id),
                    to_name="Destination",
                    depart=last_arrive,
                    arrive=final.arrival,
                    distance_m=dist,
                ))

        return RouteOption(
            legs=legs,
            depart=query_depart,
            arrive=final.arrival,
            transfers=final.transfers,
            walk_m=final.walk_m,
        )


def _hhmm_to_seconds(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 3600 + int(m) * 60


def demo():
    router = TransitRouter()
    today = date.today()
    n = router.load_service_day(today)
    print(f"Loaded {n:,} connections for {today} ({today.strftime('%A')})")
    if n == 0:
        print("No service today - try a weekday within the calendar window.")
        return

    origin = router.stop_coords.get("100")     # McQuay Northbound @ Dundas
    dest = router.stop_coords.get("1000")      # Glen Northbound @ Medina
    if not origin or not dest:
        print("demo stops missing from feed")
        return

    depart = _hhmm_to_seconds("08:30")
    options = router.route(origin[0], origin[1], dest[0], dest[1], depart)
    print(f"\n{len(options)} Pareto-optimal option(s) departing after 08:30:")
    for k, opt in enumerate(options, 1):
        print(f"\n--- Option {k}: {format_gtfs_time(opt.depart)} -> "
              f"{format_gtfs_time(opt.arrive)} "
              f"({opt.duration_s // 60} min, {opt.transfers} transfer(s), "
              f"{opt.walk_m:.0f} m walking)")
        for leg in opt.legs:
            if leg.mode == "transit":
                print(f"  [{format_gtfs_time(leg.depart)}] Board Route "
                      f"{leg.route_name} ({leg.headsign}) at {leg.from_name}")
                print(f"  [{format_gtfs_time(leg.arrive)}] Alight at "
                      f"{leg.to_name} ({leg.num_stops} stops)")
            else:
                print(f"  [{format_gtfs_time(leg.depart)}] Walk "
                      f"{leg.distance_m:.0f} m to destination "
                      f"(arrive {format_gtfs_time(leg.arrive)})")


if __name__ == "__main__":
    demo()
