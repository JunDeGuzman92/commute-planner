"""Multimodal trip comparison: drive / cycle / walk / Uber / taxi vs DRT.

Non-transit modes use the public OSRM demo server for routing (no API key).
Uber/taxi costs are local rate models (no API needed). DRT fares come from
the published 2026 fare table. Every mode reports time, cost, CO2 and
calories so the frontend can show a true apples-to-apples comparison.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import requests

from router import haversine_m

OSRM_BASE = "https://router.project-osrm.org/route/v1"
OSRM_TIMEOUT = 8

# Simple in-memory cache so repeated comparisons don't hammer OSRM.
_osrm_cache: dict[tuple, tuple[float, dict | None]] = {}
OSRM_CACHE_TTL = 300  # seconds

# --- Durham / Ontario cost & emission models -------------------------------

# DRT 2026 fares (durhamregiontransit.com/fares-passes/fares/)
DRT_FARE_PRESTO = 3.84
DRT_FARE_CASH = 4.85
DRT_MONTHLY_PASS = 138.24
DRT_GO_COFARE = 0.0  # free when connecting to/from GO

# UberX Toronto-area model (Durham rides use the same rate card)
UBER_BASE = 4.25
UBER_PER_KM = 1.26
UBER_PER_MIN = 0.38
UBER_MIN_FARE = 8.00

# Licensed taxi tariff (typical Durham meter)
TAXI_BASE = 4.75
TAXI_PER_KM = 2.10

# Driving: CRA 2026 automobile allowance as the all-in per-km cost
CAR_PER_KM = 0.70
PARKING_COST = 5.00  # rough all-day municipal parking in urban Durham

# CO2 kg per passenger-km (Ontario grid + fleet averages)
CO2_CAR = 0.192
CO2_BUS = 0.089   # DRT fleet mix incl. diesel/hybrid; EV transition underway
CO2_UBER = 0.192

# Energy burn
KCAL_WALK_PER_KM = 55
KCAL_CYCLE_PER_KM = 30

CYCLE_SPEED_KMH = 15.5  # casual urban cycling
WALK_SPEED_KMH = 5.0

# Thresholds above which a mode is impractical
MAX_PRACTICAL_WALK_KM = 5.0
MAX_PRACTICAL_CYCLE_KM = 20.0


@dataclass
class ModeOption:
    """One way of making the trip, fully costed."""
    mode: str                       # transit | drive | cycle | walk | uber | taxi
    available: bool
    duration_min: float = 0.0
    distance_km: float = 0.0
    cost: float = 0.0               # CAD, one-way
    co2_kg: float = 0.0
    calories: float = 0.0
    transfers: int = 0
    summary: str = ""
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # For transit: carries the legs through so the frontend can draw them.
    route: dict | None = None
    # Geometry for non-transit modes (GeoJSON LineString from OSRM)
    geometry: dict | None = None


def _osrm_route(profile: str, from_lat: float, from_lon: float,
                to_lat: float, to_lon: float) -> dict | None:
    """Query OSRM demo server. Returns {distance_m, duration_s, geometry}."""
    key = (profile, round(from_lat, 4), round(from_lon, 4),
           round(to_lat, 4), round(to_lon, 4))
    now = time.time()
    if key in _osrm_cache:
        ts, cached = _osrm_cache[key]
        if now - ts < OSRM_CACHE_TTL:
            return cached

    url = (f"{OSRM_BASE}/{profile}/"
           f"{from_lon},{from_lat};{to_lon},{to_lat}"
           f"?overview=full&geometries=geojson")
    try:
        resp = requests.get(url, timeout=OSRM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            _osrm_cache[key] = (now, None)
            return None
        r = data["routes"][0]
        out = {
            "distance_m": r["distance"],
            "duration_s": r["duration"],
            "geometry": r["geometry"],
        }
        _osrm_cache[key] = (now, out)
        return out
    except Exception:
        _osrm_cache[key] = (now, None)
        return None


def drive_option(from_lat: float, from_lon: float,
                 to_lat: float, to_lon: float) -> ModeOption:
    r = _osrm_route("driving", from_lat, from_lon, to_lat, to_lon)
    if not r:
        return ModeOption("drive", False, warnings=["Driving route unavailable"])
    km = r["distance_m"] / 1000
    mins = r["duration_s"] / 60
    cost = km * CAR_PER_KM + PARKING_COST
    return ModeOption(
        mode="drive",
        available=True,
        duration_min=round(mins, 1),
        distance_km=round(km, 2),
        cost=round(cost, 2),
        co2_kg=round(km * CO2_CAR, 2),
        calories=0,
        summary=f"Drive {km:.1f} km",
        reasons=[f"{mins:.0f} min door-to-door", "No schedule constraints"],
        warnings=[f"Includes ~${PARKING_COST:.0f} parking estimate"],
        geometry=r["geometry"],
    )


def cycle_option(from_lat: float, from_lon: float,
                 to_lat: float, to_lon: float) -> ModeOption:
    r = _osrm_route("cycling", from_lat, from_lon, to_lat, to_lon)
    km = (r["distance_m"] / 1000) if r else haversine_m(
        from_lat, from_lon, to_lat, to_lon) / 1000
    if km > MAX_PRACTICAL_CYCLE_KM:
        return ModeOption("cycle", False,
                          warnings=[f"{km:.1f} km exceeds practical cycling range"])
    mins = km / CYCLE_SPEED_KMH * 60
    return ModeOption(
        mode="cycle",
        available=True,
        duration_min=round(mins, 1),
        distance_km=round(km, 2),
        cost=0.0,
        co2_kg=0.0,
        calories=round(km * KCAL_CYCLE_PER_KM),
        summary=f"Cycle {km:.1f} km",
        reasons=["Free", f"~{km * KCAL_CYCLE_PER_KM:.0f} kcal"],
        warnings=[] if r else ["Route geometry unavailable — showing estimate"],
        geometry=r["geometry"] if r else None,
    )


def walk_option(from_lat: float, from_lon: float,
                to_lat: float, to_lon: float) -> ModeOption:
    km = haversine_m(from_lat, from_lon, to_lat, to_lon) / 1000
    if km > MAX_PRACTICAL_WALK_KM:
        return ModeOption("walk", False,
                          warnings=[f"{km:.1f} km exceeds practical walking range"])
    mins = km / WALK_SPEED_KMH * 60
    return ModeOption(
        mode="walk",
        available=True,
        duration_min=round(mins, 1),
        distance_km=round(km, 2),
        cost=0.0,
        co2_kg=0.0,
        calories=round(km * KCAL_WALK_PER_KM),
        summary=f"Walk {km:.1f} km",
        reasons=["Free", f"~{km * KCAL_WALK_PER_KM:.0f} kcal"],
    )


def uber_option(from_lat: float, from_lon: float,
                to_lat: float, to_lon: float) -> ModeOption:
    r = _osrm_route("driving", from_lat, from_lon, to_lat, to_lon)
    if not r:
        return ModeOption("uber", False, warnings=["Route unavailable"])
    km = r["distance_m"] / 1000
    mins = r["duration_s"] / 60
    cost = max(UBER_MIN_FARE, UBER_BASE + km * UBER_PER_KM + mins * UBER_PER_MIN)
    return ModeOption(
        mode="uber",
        available=True,
        duration_min=round(mins + 5, 1),  # +5 min average pickup wait
        distance_km=round(km, 2),
        cost=round(cost, 2),
        co2_kg=round(km * CO2_UBER, 2),
        calories=0,
        summary=f"Uber {km:.1f} km",
        reasons=["Door-to-door", f"~{mins + 5:.0f} min incl. pickup"],
        warnings=["Estimated fare — surge pricing may apply"],
        geometry=r["geometry"],
    )


def taxi_option(from_lat: float, from_lon: float,
                to_lat: float, to_lon: float) -> ModeOption:
    r = _osrm_route("driving", from_lat, from_lon, to_lat, to_lon)
    if not r:
        return ModeOption("taxi", False, warnings=["Route unavailable"])
    km = r["distance_m"] / 1000
    mins = r["duration_s"] / 60
    cost = TAXI_BASE + km * TAXI_PER_KM
    return ModeOption(
        mode="taxi",
        available=True,
        duration_min=round(mins + 8, 1),  # +8 min dispatch wait
        distance_km=round(km, 2),
        cost=round(cost, 2),
        co2_kg=round(km * CO2_UBER, 2),
        calories=0,
        summary=f"Taxi {km:.1f} km",
        reasons=["Door-to-door", "Metered tariff"],
        warnings=["Estimated fare — actual meter may vary"],
        geometry=r["geometry"],
    )


def transit_option(routes: list[dict]) -> ModeOption:
    """Wrap the best (fastest) transit route as a comparable ModeOption.

    Cost: DRT charges per boarding, but a 2-hour transfer window means most
    trips cost a single PRESTO tap. We model one fare per journey.
    """
    if not routes:
        return ModeOption("transit", False,
                          warnings=["No transit route found for this time"])
    best = min(routes, key=lambda r: r["duration_min"])
    km = sum(l.get("distance_m", 0) for l in best["legs"]
             if l["mode"] == "transit") / 1000
    opt = ModeOption(
        mode="transit",
        available=True,
        duration_min=best["duration_min"],
        distance_km=round(km, 2),
        cost=DRT_FARE_PRESTO,
        co2_kg=round(km * CO2_BUS, 2),
        calories=round(best["walk_m"] / 1000 * KCAL_WALK_PER_KM),
        transfers=best["transfers"],
        summary=f"DRT bus, {best['transfers']} transfer(s)",
        reasons=[f"${DRT_FARE_PRESTO:.2f} with PRESTO",
                 "Free transfer window (2 hrs)"],
        route=best,
    )
    if best["transfers"] >= 2:
        opt.warnings.append(f"{best['transfers']} transfers — higher delay risk")
    return opt


def compare_modes(from_lat: float, from_lon: float, to_lat: float,
                  to_lon: float, transit_routes: list[dict]) -> list[ModeOption]:
    """Cost every mode and return the full comparison set."""
    return [
        transit_option(transit_routes),
        drive_option(from_lat, from_lon, to_lat, to_lon),
        cycle_option(from_lat, from_lon, to_lat, to_lon),
        walk_option(from_lat, from_lon, to_lat, to_lon),
        uber_option(from_lat, from_lon, to_lat, to_lon),
        taxi_option(from_lat, from_lon, to_lat, to_lon),
    ]
