"""Recommendation engine: scores each mode and explains its reasoning.

Not a black box — every recommendation comes with human-readable reasons
so the user can sanity-check it. Scores are 0-100 per criterion, weighted
by a user profile (balanced / cheapest / fastest / greenest / healthiest).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from modes import ModeOption, DRT_FARE_PRESTO, DRT_MONTHLY_PASS

PROFILES = {
    #            time    cost   green  health
    "balanced":  (0.40,  0.30,  0.15,  0.15),
    "cheapest":  (0.15,  0.55,  0.15,  0.15),
    "fastest":   (0.65,  0.10,  0.10,  0.15),
    "greenest":  (0.20,  0.15,  0.55,  0.10),
    "healthiest": (0.15, 0.15,  0.10,  0.60),
}

@dataclass
class ScoredMode:
    option: ModeOption
    score: float
    badges: list[str] = field(default_factory=list)
    why: list[str] = field(default_factory=list)


def _norm(values: list[float], v: float, invert: bool = False) -> float:
    """Min-max normalize to 0-100. invert=True when lower is better."""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return 100.0
    x = (v - lo) / (hi - lo)
    return (1 - x if invert else x) * 100


def recommend(options: list[ModeOption], profile: str = "balanced",
              transit_delay_risk: float = 0.0) -> list[ScoredMode]:
    """Score all available modes. transit_delay_risk: 0-1 probability signal
    from real-time data (fraction of relevant trips currently delayed)."""
    avail = [o for o in options if o.available]
    if not avail:
        return []

    w_time, w_cost, w_green, w_health = PROFILES.get(profile, PROFILES["balanced"])

    times = [o.duration_min for o in avail]
    costs = [o.cost for o in avail]
    co2s = [o.co2_kg for o in avail]
    cals = [o.calories for o in avail]

    scored: list[ScoredMode] = []
    for o in avail:
        s_time = _norm(times, o.duration_min, invert=True)
        # Penalize transit time by its delay risk so a late network drops its score
        if o.mode == "transit":
            s_time *= (1 - 0.4 * transit_delay_risk)
        s_cost = _norm(costs, o.cost, invert=True)
        s_green = _norm(co2s, o.co2_kg, invert=True)
        s_health = _norm(cals, o.calories)  # more burn = better

        total = (w_time * s_time + w_cost * s_cost +
                 w_green * s_green + w_health * s_health)

        sm = ScoredMode(option=o, score=round(total, 1))

        # --- explainable badges ---
        if o.duration_min == min(times):
            sm.badges.append("Fastest")
        if o.cost == min(costs):
            sm.badges.append("Cheapest")
        if o.co2_kg == min(co2s):
            sm.badges.append("Lowest CO2")
        if o.calories == max(cals) and o.calories > 0:
            sm.badges.append("Most active")

        # --- why this mode, in plain language ---
        if o.mode == "transit":
            sm.why.append(f"${o.cost:.2f} vs ${max(costs):.2f} most expensive option")
            if transit_delay_risk > 0.3:
                sm.why.append(f"Network delays elevated right now — "
                              f"reliability discounted")
            if o.transfers == 0:
                sm.why.append("No transfers")
        elif o.mode == "drive":
            sm.why.append(f"Door-to-door in {o.duration_min:.0f} min")
            sm.why.append(f"True cost ~${o.cost:.2f}/trip incl. parking & wear")
        elif o.mode in ("uber", "taxi"):
            sm.why.append("Door-to-door, no parking")
            sm.why.append(f"~${o.cost:.2f} estimated")
        elif o.mode in ("walk", "cycle"):
            sm.why.append("Free and zero emissions")
            sm.why.append(f"~{o.calories:.0f} kcal burned")

        scored.append(sm)

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def monthly_breakeven(trips_per_week: int) -> dict:
    """When does a DRT monthly pass beat pay-per-ride?"""
    monthly_trips = trips_per_week * 4.33
    payg = monthly_trips * DRT_FARE_PRESTO
    saves = payg > DRT_MONTHLY_PASS
    return {
        "trips_per_month": round(monthly_trips),
        "pay_per_ride_cost": round(payg, 2),
        "monthly_pass_cost": DRT_MONTHLY_PASS,
        "pass_saves_money": saves,
        "monthly_savings": round(payg - DRT_MONTHLY_PASS, 2) if saves else 0.0,
        "breakeven_trips_per_week": round(DRT_MONTHLY_PASS / DRT_FARE_PRESTO / 4.33, 1),
    }
