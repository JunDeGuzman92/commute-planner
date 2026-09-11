"""FastAPI service exposing the commute planner.

Endpoints:
  GET  /health       - service + feed status
  GET  /stops        - stop search by name (for the frontend autocomplete)
  POST /plan         - Pareto-optimal routes between two coordinates
  GET  /vehicles     - live bus positions (for map display)
  GET  /alerts       - active service alerts
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from realtime import RealtimePoller, RealtimeStore
from router import TransitRouter, format_gtfs_time

rt_store = RealtimeStore()
poller = RealtimePoller(rt_store)
router = TransitRouter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load today's connections and start the realtime poller.
    router.load_service_day(date.today())
    poller.start()
    yield
    poller.stop()


app = FastAPI(title="Durham Commute Planner API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # locked down once the frontend URL is known
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlanRequest(BaseModel):
    from_lat: float = Field(..., ge=-90, le=90)
    from_lon: float = Field(..., ge=-180, le=180)
    to_lat: float = Field(..., ge=-90, le=90)
    to_lon: float = Field(..., ge=-180, le=180)
    depart_at: str | None = None  # "HH:MM", defaults to now
    max_walk_m: float = 1200
    use_realtime: bool = True


class LegOut(BaseModel):
    mode: str
    from_name: str
    to_name: str
    depart: str
    arrive: str
    route_name: str | None = None
    headsign: str | None = None
    num_stops: int = 0
    distance_m: float = 0.0
    geometry: dict | None = None  # GeoJSON LineString for transit legs
    from_lat: float | None = None
    from_lon: float | None = None
    to_lat: float | None = None
    to_lon: float | None = None


class RouteOut(BaseModel):
    depart: str
    arrive: str
    duration_min: int
    transfers: int
    walk_m: float
    legs: list[LegOut]


@app.get("/health")
def health():
    return {
        "status": "ok",
        "connections_loaded": len(router.connections),
        "realtime": rt_store.status(),
    }


@app.get("/stops")
def search_stops(q: str = Query(..., min_length=2), limit: int = 10):
    q_lower = q.lower()
    matches = [
        {
            "stop_id": s["stop_id"],
            "name": s["stop_name"],
            "lat": s["stop_lat"],
            "lon": s["stop_lon"],
        }
        for s in router.stops.values()
        if q_lower in (s["stop_name"] or "").lower()
    ]
    return matches[:limit]


@app.post("/plan", response_model=list[RouteOut])
def plan(req: PlanRequest):
    today = date.today()
    if req.depart_at:
        h, m = req.depart_at.split(":")
        depart = int(h) * 3600 + int(m) * 60
    else:
        now = datetime.now()
        depart = now.hour * 3600 + now.minute * 60 + now.second

    options = router.route(
        req.from_lat,
        req.from_lon,
        req.to_lat,
        req.to_lon,
        depart,
        max_walk_m=req.max_walk_m,
        rt_store=rt_store if req.use_realtime else None,
        service_date=today if req.use_realtime else None,
    )
    return [
        RouteOut(
            depart=format_gtfs_time(o.depart),
            arrive=format_gtfs_time(o.arrive),
            duration_min=o.duration_s // 60,
            transfers=o.transfers,
            walk_m=round(o.walk_m),
            legs=[
                LegOut(
                    mode=leg.mode,
                    from_name=leg.from_name,
                    to_name=leg.to_name,
                    depart=format_gtfs_time(leg.depart),
                    arrive=format_gtfs_time(leg.arrive),
                    route_name=leg.route_name,
                    headsign=leg.headsign,
                    num_stops=leg.num_stops,
                    distance_m=round(leg.distance_m),
                    geometry=router.get_leg_geometry(
                        leg.trip_id, leg.from_stop, leg.to_stop
                    ) if leg.mode == "transit" and leg.trip_id else None,
                    from_lat=router.stop_coords.get(leg.from_stop, (None, None))[0],
                    from_lon=router.stop_coords.get(leg.from_stop, (None, None))[1],
                    to_lat=router.stop_coords.get(leg.to_stop, (None, None))[0],
                    to_lon=router.stop_coords.get(leg.to_stop, (None, None))[1],
                )
                for leg in o.legs
            ],
        )
        for o in options
    ]


@app.get("/vehicles")
def vehicles():
    return [
        {
            "trip_id": v.trip_id,
            "vehicle_id": v.vehicle_id,
            "lat": v.lat,
            "lon": v.lon,
        }
        for v in rt_store.vehicles()
    ]


@app.get("/alerts")
def alerts():
    return rt_store.alerts()
