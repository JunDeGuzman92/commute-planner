"""What-if scenario analysis.

Answers the questions a commuter actually asks:
  - "What if I miss this bus?" (replan at the next departure)
  - "What if I leave 15/30 min later?" (arrival shift curve)
  - "What if it's raining/snowing?" (mode viability + recommendation flip)
  - "Should I get a monthly pass?" (break-even math)
  - "What if the network is delayed?" (real-time risk signal)

Weather comes from Open-Meteo — free, no API key required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes (subset)
WMO_RAIN = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
WMO_SNOW = {71, 73, 75, 77, 85, 86}
WMO_STORM = {95, 96, 99}


@dataclass
class ScenarioResult:
    scenario: str
    headline: str
    detail: str
    # Optional structured payloads the frontend can render
    timeline: list[dict] = field(default_factory=list)   # leave-later curve
    alternatives: list[dict] = field(default_factory=list)  # next departures
    weather: dict | None = None
    breakeven: dict | None = None


def get_weather(lat: float, lon: float) -> dict:
    """Current conditions for scenario analysis. Fails soft."""
    try:
        resp = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,precipitation,weather_code,"
                           "wind_speed_10m",
                "forecast_days": 1,
            },
            timeout=6,
        )
        resp.raise_for_status()
        cur = resp.json()["current"]
        code = cur["weather_code"]
        condition = "clear"
        if code in WMO_STORM:
            condition = "storm"
        elif code in WMO_SNOW:
            condition = "snow"
        elif code in WMO_RAIN:
            condition = "rain"
        return {
            "temp_c": cur["temperature_2m"],
            "precip_mm": cur["precipitation"],
            "wind_kmh": cur["wind_speed_10m"],
            "condition": condition,
            "code": code,
        }
    except Exception:
        return {"condition": "unknown"}


def weather_scenario(weather: dict, modes: list) -> ScenarioResult:
    """Adjust mode advice for current weather."""
    cond = weather.get("condition", "unknown")
    temp = weather.get("temp_c")

    if cond in ("rain", "snow", "storm"):
        headline = f"It's {cond}ing right now"
        details = []
        if cond == "storm":
            details.append("Thunderstorms — avoid cycling and walking")
        elif cond == "snow":
            details.append("Snow slows buses and makes cycling hazardous")
        else:
            details.append("Rain makes cycling uncomfortable; expect bus crowding")
        if temp is not None and temp < 5:
            details.append(f"{temp:.0f}°C — cold exposure risk on long walks")
        advice = ("Transit or rideshare is the practical choice today. "
                  "Cycling/walking scored down automatically.")
        return ScenarioResult("weather", headline, advice + " " + " ".join(details),
                              weather=weather)

    headline = "Weather is clear"
    if temp is not None and 10 <= temp <= 28:
        advice = (f"{temp:.0f}°C and dry — ideal conditions for cycling "
                  "or walking if distance allows.")
    else:
        advice = "No weather-related impact on any mode."
    return ScenarioResult("weather", headline, advice, weather=weather)


def missed_bus_scenario(next_routes: list[dict], current_arrive: str) -> ScenarioResult:
    """User missed the suggested departure — here's the next option."""
    if not next_routes:
        return ScenarioResult(
            "missed_bus",
            "No later departures found",
            "This may be the last practical trip today. Check DRT On Demand "
            "(1-866-247-0055) or consider rideshare.",
        )
    nxt = next_routes[0]
    gap = nxt["depart"]
    detail = (f"Next option leaves {gap}, arrives {nxt['arrive']} "
              f"({nxt['duration_min']} min, {nxt['transfers']} transfer(s)).")
    return ScenarioResult(
        "missed_bus",
        f"If you miss it: next departure {gap}",
        detail,
        alternatives=[{
            "depart": r["depart"], "arrive": r["arrive"],
            "duration_min": r["duration_min"], "transfers": r["transfers"],
        } for r in next_routes[:3]],
    )


def leave_later_curve(router, rt_store, from_lat, from_lon, to_lat, to_lon,
                      depart_s: int, max_walk_m: float,
                      offsets=(0, 15, 30, 45, 60)) -> ScenarioResult:
    """Arrival times if you shift departure by 15-60 minutes."""
    from router import format_gtfs_time
    from datetime import date

    points = []
    for off in offsets:
        t = depart_s + off * 60
        opts = router.route(from_lat, from_lon, to_lat, to_lon, t,
                            max_walk_m=max_walk_m,
                            rt_store=rt_store, service_date=date.today())
        if opts:
            best = min(opts, key=lambda o: o.duration_s)
            points.append({
                "offset_min": off,
                "depart": format_gtfs_time(best.depart),
                "arrive": format_gtfs_time(best.arrive),
                "duration_min": best.duration_s // 60,
            })
        else:
            points.append({"offset_min": off, "depart": None, "arrive": None,
                           "duration_min": None})

    found = [p for p in points if p["depart"]]
    if len(found) >= 2:
        spread = max(p["duration_min"] for p in found) - min(
            p["duration_min"] for p in found)
        detail = (f"Trips vary by {spread} min across the next hour. "
                  f"{'Leaving later costs little — flexible window.' if spread <= 10 else 'Timing matters: pick your departure carefully.'}")
    else:
        detail = "Limited service in this window."
    return ScenarioResult("leave_later", "Leave-later curve", detail,
                          timeline=points)
