"""Commuter plan intelligence: the strategic layer above raw routing.

Raw answers tell you *what* the options are. Insights tell you what they
*mean* for your life:

  - Time-value: cycling saves $18.50 vs driving but takes 28 min longer.
    That's like earning $39/hr tax-free — better than most part-time jobs.
  - Fragility: a route with a 3-minute transfer misses ~25% of the time
    when the network is running 5 min late. We flag it before you learn
    the hard way.
  - Departure windows: scan the morning and find where small shifts
    buy big time savings (or cost them).
  - Weekly optimizer: mixing modes across a week beats picking one —
    cycle sunny days, transit rainy ones, and the savings compound.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date

from modes import ModeOption
from router import format_gtfs_time

# Connection-tightness → miss probability, calibrated to typical transit
# reliability (buses on urban arterials, 5-min stddev lateness).
# (slack_minutes, base_miss_probability)
FRAGILITY_TABLE = [
    (2, 0.45),
    (4, 0.30),
    (6, 0.18),
    (9, 0.10),
    (12, 0.05),
    (999, 0.02),
]


@dataclass
class Insight:
    kind: str          # time_value | fragility | departure_window | weekly_plan
    headline: str
    detail: str
    data: dict = field(default_factory=dict)


def _miss_probability(slack_min: float, delay_risk: float) -> float:
    base = next(p for s, p in FRAGILITY_TABLE if slack_min <= s)
    # Elevated network delays shift everything up
    return min(0.95, base * (1 + 1.5 * delay_risk))


def time_value_insight(options: list[ModeOption]) -> Insight | None:
    """Translate cost-vs-time trade-offs into an effective hourly rate —
    the single most intuitive way to compare modes."""
    avail = [o for o in options if o.available and o.mode != "walk"]
    if len(avail) < 2:
        return None

    # Cheapest vs fastest anchors the trade-off line
    cheapest = min(avail, key=lambda o: o.cost)
    fastest = min(avail, key=lambda o: o.duration_min)
    if cheapest.mode == fastest.mode:
        return Insight(
            "time_value",
            f"{fastest.mode.title()} is both cheapest and fastest",
            "No trade-off to analyze — take it.",
        )

    saved = fastest.cost - cheapest.cost
    extra_min = cheapest.duration_min - fastest.duration_min
    if extra_min <= 0 or saved <= 0:
        return None

    rate = saved / (extra_min / 60)
    verdict = (
        "well worth it — better than most part-time wages, and it's tax-free"
        if rate >= 20
        else "a reasonable trade if you're not rushed"
        if rate >= 12
        else "a poor trade — your time is likely worth more"
    )
    return Insight(
        "time_value",
        f"Choosing {cheapest.mode} over {fastest.mode} pays you ${rate:.0f}/hour",
        f"You save ${saved:.2f} for {extra_min:.0f} extra minutes — {verdict}.",
        data={"hourly_rate": round(rate, 2), "saved": round(saved, 2),
              "extra_minutes": round(extra_min),
              "slower_mode": cheapest.mode, "faster_mode": fastest.mode},
    )


def fragility_insight(route: dict, delay_risk: float) -> Insight | None:
    """Score the tightest connection in a transit route.

    Walk legs between transit legs are transfers; the gap between alight
    and board times is the slack. Tight slack + delayed network = missed
    connections.
    """
    legs = route.get("legs", [])
    slacks = []
    for i in range(len(legs) - 1):
        a, b = legs[i], legs[i + 1]
        if a["mode"] == "transit" and b["mode"] == "transit":
            # times are HH:MM strings
            ah, am = map(int, a["arrive"].split(":"))
            bh, bm = map(int, b["depart"].split(":"))
            slacks.append((bh * 60 + bm) - (ah * 60 + am))

    if not slacks:
        return Insight(
            "fragility", "Direct ride — no connections to miss",
            "A single-vehicle trip is the most reliable transit option.",
            data={"transfers": 0, "worst_slack_min": None, "miss_risk": 0},
        )

    worst = min(slacks)
    risk = _miss_probability(worst, delay_risk)
    if risk >= 0.30:
        headline = f"Risky connection: {worst} min transfer, ~{risk:.0%} miss chance"
        detail = ("If you miss it, you're waiting for the next bus on that "
                  "leg. Consider the earlier departure or an alternative "
                  "route with a longer layover.")
    elif risk >= 0.12:
        headline = f"Workable connection: {worst} min transfer, ~{risk:.0%} miss chance"
        detail = ("Usually fine, but watch live delays on your first bus "
                  "before committing.")
    else:
        headline = f"Comfortable connection: {worst} min transfer"
        detail = "Enough slack to absorb normal delays."

    return Insight(
        "fragility", headline, detail,
        data={"transfers": len(slacks), "worst_slack_min": worst,
              "miss_risk": round(risk, 2)},
    )


def departure_window_insight(router, rt_store, from_lat, from_lon,
                             to_lat, to_lon, base_depart_s: int,
                             max_walk_m: float,
                             window_min: int = 120) -> Insight | None:
    """Scan ±window around the requested departure in 10-min steps and find
    where the commute is fastest — and where the cliff edges are."""
    samples = []
    for off in range(-window_min, window_min + 1, 10):
        t = base_depart_s + off * 60
        if t < 0:
            continue
        opts = router.route(from_lat, from_lon, to_lat, to_lon, t,
                            max_walk_m=max_walk_m, rt_store=rt_store,
                            service_date=date.today())
        if opts:
            best = min(opts, key=lambda o: o.duration_s)
            samples.append((off, best.duration_s // 60))

    if len(samples) < 4:
        return None

    best_off, best_dur = min(samples, key=lambda s: s[1])
    base = next((d for o, d in samples if o == 0), None)
    durations = [d for _, d in samples]

    # Detect cliffs: adjacent samples jumping >20 min
    cliffs = [(samples[i][0], samples[i + 1][1] - samples[i][1])
              for i in range(len(samples) - 1)
              if samples[i + 1][1] - samples[i][1] >= 20]

    if best_off == 0:
        headline = "You're already departing in the best window"
        detail = f"Trips within ±{window_min} min range from " \
                 f"{min(durations)} to {max(durations)} min."
    else:
        saving = (base - best_dur) if base else 0
        headline = (f"Leave {abs(best_off)} min "
                    f"{'earlier' if best_off < 0 else 'later'}: "
                    f"save {saving} min")
        detail = (f"The {format_gtfs_time(base_depart_s + best_off * 60)} "
                  f"departure is the fastest in this window "
                  f"({best_dur} min vs your {base} min).")

    if cliffs:
        worst_cliff = max(cliffs, key=lambda c: c[1])
        detail += (f" Warning: departing after "
                   f"{format_gtfs_time(base_depart_s + worst_cliff[0] * 60)} "
                   f"adds ~{worst_cliff[1]} min — that's the service gap.")

    return Insight(
        "departure_window", headline, detail,
        data={"samples": [{"offset_min": o, "duration_min": d}
                          for o, d in samples],
              "best_offset_min": best_off, "best_duration_min": best_dur},
    )


def weekly_plan_insight(options: list[ModeOption], forecast: list[dict],
                        trips_per_week: int, monthly_budget: float) -> Insight | None:
    """Optimize the mode mix across a commuting week.

    Strategy: cycle the dry days, transit the wet ones, and only rideshare
    when neither works. Report the projected monthly cost and savings vs
    the single-mode default.
    """
    if not forecast or not options:
        return None

    avail = {o.mode: o for o in options if o.available}
    if "transit" not in avail:
        return None

    cycle_ok = "cycle" in avail
    dry_days = sum(1 for d in forecast[:5]
                   if d.get("condition") in ("clear", "unknown"))
    wet_days = 5 - dry_days

    transit_cost = avail["transit"].cost * 2  # round trip
    cycle_cost = 0.0

    if cycle_ok and dry_days > 0:
        weekly = (dry_days * cycle_cost + wet_days * transit_cost)
        plan = (f"Cycle {dry_days} dry day{'s' if dry_days != 1 else ''}, "
                f"transit {wet_days} wet day{'s' if wet_days != 1 else ''}")
    else:
        weekly = 5 * transit_cost
        plan = "Transit all week — no dry cycling days ahead"

    monthly = weekly * 4.33
    all_transit_monthly = 5 * transit_cost * 4.33
    saved = all_transit_monthly - monthly

    if monthly_budget and monthly > monthly_budget:
        budget_note = (f" This is ${monthly - monthly_budget:.0f} over your "
                       f"monthly budget — consider swapping one more day to "
                       f"cycling or check the monthly pass math.")
    else:
        budget_note = ""

    return Insight(
        "weekly_plan",
        f"This week: {plan}",
        f"Projected ${monthly:.0f}/month vs ${all_transit_monthly:.0f} "
        f"all-transit — saving ${saved:.0f}.{budget_note}",
        data={"dry_days": dry_days, "wet_days": wet_days,
              "weekly_cost": round(weekly, 2),
              "monthly_cost": round(monthly, 2),
              "monthly_savings_vs_transit": round(saved, 2)},
    )
