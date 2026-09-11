"""FastAPI service exposing the commute planner.

Endpoints:
  GET  /health       - service + feed status
  GET  /stops        - stop search by name (for the frontend autocomplete)
  POST /plan         - Pareto-optimal routes between two coordinates
  POST /compare      - all modes (transit/drive/cycle/walk/uber/taxi) scored
  POST /whatif       - scenario analysis (missed bus, leave later, weather, pass)
  POST /intercity    - GO/VIA/Megabus/FlixBus/Poparide options
  POST /budget       - budget comparison + AI surplus advisor
  GET  /vehicles     - live bus positions (for map display)
  GET  /alerts       - active service alerts
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date, datetime

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from budget import BudgetState, advise_surplus, compare_all_vs_budget
from intercity import intercity_options
from modes import compare_modes
from recommend import recommend, monthly_breakeven
from realtime import RealtimePoller, RealtimeStore
from router import TransitRouter, format_gtfs_time
from whatif import (get_weather, weather_scenario, missed_bus_scenario,
                    leave_later_curve)

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


def _serialize_routes(options) -> list[dict]:
    """Route objects -> plain dicts used by /plan, /compare, /whatif."""
    return [
        {
            "depart": format_gtfs_time(o.depart),
            "arrive": format_gtfs_time(o.arrive),
            "duration_min": o.duration_s // 60,
            "transfers": o.transfers,
            "walk_m": round(o.walk_m),
            "legs": [
                {
                    "mode": leg.mode,
                    "from_name": leg.from_name,
                    "to_name": leg.to_name,
                    "depart": format_gtfs_time(leg.depart),
                    "arrive": format_gtfs_time(leg.arrive),
                    "route_name": leg.route_name,
                    "headsign": leg.headsign,
                    "num_stops": leg.num_stops,
                    "distance_m": round(leg.distance_m),
                    "geometry": router.get_leg_geometry(
                        leg.trip_id, leg.from_stop, leg.to_stop
                    ) if leg.mode == "transit" and leg.trip_id else None,
                    "from_lat": router.stop_coords.get(leg.from_stop, (None, None))[0],
                    "from_lon": router.stop_coords.get(leg.from_stop, (None, None))[1],
                    "to_lat": router.stop_coords.get(leg.to_stop, (None, None))[0],
                    "to_lon": router.stop_coords.get(leg.to_stop, (None, None))[1],
                }
                for leg in o.legs
            ],
        }
        for o in options
    ]


def _run_transit_query(req: PlanRequest):
    """Shared transit routing used by /plan, /compare, /whatif."""
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
    return _serialize_routes(options), depart


def _delay_risk() -> float:
    """Fraction of currently tracked trips running >5 min late."""
    delays = rt_store.current_delays()
    if not delays:
        return 0.0
    late = sum(1 for d in delays.values() if d > 300)
    return late / len(delays)


class CompareRequest(PlanRequest):
    profile: str = "balanced"  # balanced|cheapest|fastest|greenest|healthiest


class WhatIfRequest(PlanRequest):
    scenario: str  # missed_bus | leave_later | weather | monthly_pass
    trips_per_week: int = 10  # for monthly_pass


@app.post("/plan", response_model=list[RouteOut])
def plan(req: PlanRequest):
    routes, _ = _run_transit_query(req)
    return routes


@app.post("/compare")
def compare(req: CompareRequest):
    """Cost every mode side-by-side with a recommendation."""
    routes, _ = _run_transit_query(req)
    options = compare_modes(req.from_lat, req.from_lon,
                            req.to_lat, req.to_lon, routes)
    scored = recommend(options, profile=req.profile,
                       transit_delay_risk=_delay_risk())
    return {
        "modes": [
            {
                **asdict(s.option),
                "score": s.score,
                "badges": s.badges,
                "why": s.why,
            }
            for s in scored
        ],
        "recommended": scored[0].option.mode if scored else None,
        "delay_risk": round(_delay_risk(), 2),
    }


@app.post("/whatif")
def whatif(req: WhatIfRequest):
    """Scenario analysis."""
    routes, depart_s = _run_transit_query(req)

    if req.scenario == "weather":
        w = get_weather(req.from_lat, req.from_lon)
        result = weather_scenario(w, routes)

    elif req.scenario == "missed_bus":
        # Replan at the departure of the second-fastest option (i.e., the one
        # after the one you'd miss), using routes already returned.
        current_arrive = routes[0]["arrive"] if routes else None
        later = routes[1:] if len(routes) > 1 else []
        result = missed_bus_scenario(later, current_arrive or "")

    elif req.scenario == "leave_later":
        result = leave_later_curve(
            router, rt_store if req.use_realtime else None,
            req.from_lat, req.from_lon, req.to_lat, req.to_lon,
            depart_s, req.max_walk_m,
        )

    elif req.scenario == "monthly_pass":
        from dataclasses import asdict as _ad
        be = monthly_breakeven(req.trips_per_week)
        result = type("R", (), {})()
        result.scenario = "monthly_pass"
        result.headline = ("Monthly pass saves you money"
                           if be["pass_saves_money"]
                           else "Pay-per-ride is cheaper at your frequency")
        result.detail = (
            f"{be['trips_per_month']} trips/month: pay-per-ride "
            f"${be['pay_per_ride_cost']:.2f} vs pass ${be['monthly_pass_cost']:.2f}. "
            f"Break-even at {be['breakeven_trips_per_week']} trips/week.")
        result.timeline = []
        result.alternatives = []
        result.weather = None
        result.breakeven = be

    else:
        from fastapi import HTTPException
        raise HTTPException(400, f"Unknown scenario: {req.scenario}")

    return {
        "scenario": result.scenario,
        "headline": result.headline,
        "detail": result.detail,
        "timeline": result.timeline,
        "alternatives": result.alternatives,
        "weather": result.weather,
        "breakeven": result.breakeven,
    }


class IntercityRequest(BaseModel):
    from_lat: float = Field(..., ge=-90, le=90)
    from_lon: float = Field(..., ge=-180, le=180)
    to_lat: float = Field(..., ge=-90, le=90)
    to_lon: float = Field(..., ge=-180, le=180)


@app.post("/intercity")
def intercity(req: IntercityRequest):
    """GO Train, VIA Rail, Megabus, FlixBus, Poparide options."""
    opts = intercity_options(req.from_lat, req.from_lon,
                             req.to_lat, req.to_lon)
    return {"options": [asdict(o) for o in opts]}


class BudgetRequest(PlanRequest):
    monthly_budget: float = Field(..., gt=0)
    trips_per_week: int = Field(10, ge=1, le=60)
    savings_balance: float = 0.0
    food_insecure: bool = False
    profile: str = "balanced"


@app.post("/budget")
def budget(req: BudgetRequest):
    """Full budget analysis: every mode vs budget + AI surplus advice."""
    routes, _ = _run_transit_query(req)
    options = compare_modes(req.from_lat, req.from_lon,
                            req.to_lat, req.to_lon, routes)
    scored = recommend(options, profile=req.profile,
                       transit_delay_risk=_delay_risk())

    mode_dicts = [
        {**asdict(s.option), "score": s.score, "badges": s.badges}
        for s in scored
    ]

    # Default the "chosen" mode to the recommendation
    chosen = scored[0].option if scored else None
    state = BudgetState(
        monthly_budget=req.monthly_budget,
        trips_per_week=req.trips_per_week,
        chosen_mode=chosen.mode if chosen else "transit",
        cost_per_trip=chosen.cost if chosen else 0.0,
    )

    comparison = compare_all_vs_budget(state, mode_dicts)
    advice = advise_surplus(state, savings_balance=req.savings_balance,
                            food_insecure=req.food_insecure)

    return {
        "recommended_mode": chosen.mode if chosen else None,
        "comparison": comparison,
        "advisor": {
            "headline": advice.headline,
            "actions": advice.actions,
            "reasoning": advice.reasoning,
            "suggested_allocation": advice.suggested_allocation,
        },
        "budget_state": {
            "monthly_budget": state.monthly_budget,
            "monthly_spend": round(state.monthly_spend, 2),
            "surplus": round(state.surplus, 2),
            "trips_per_month": round(state.trips_per_month),
        },
    }


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
