"""Sanity checks for the router against the real DRT feed."""
import time
from datetime import date

from router import TransitRouter, _hhmm_to_seconds, format_gtfs_time

router = TransitRouter()
n = router.load_service_day(date(2026, 9, 10))  # a Thursday in window
print(f"connections: {n:,}")


def show(tag, o, d, depart):
    t0 = time.perf_counter()
    options = router.route(o[0], o[1], d[0], d[1], depart)
    ms = (time.perf_counter() - t0) * 1000
    print(f"\n{tag}: {len(options)} option(s) in {ms:.0f} ms")
    for k, opt in enumerate(options, 1):
        rides = [leg for leg in opt.legs if leg.mode == "transit"]
        names = " -> ".join(f"R{leg.route_name}" for leg in rides)
        print(
            f"  {k}. {format_gtfs_time(opt.depart)}->{format_gtfs_time(opt.arrive)}"
            f" | {opt.duration_s // 60} min | {opt.transfers} tr | "
            f"{opt.walk_m:.0f} m | {names}"
        )
    return options


# 1. Direct corridor, morning peak
o = router.stop_coords["2576"]  # Whitby Station
d = router.stop_coords["102"]   # McQuay NB @ Kennett
show("direct corridor 08:30", o, d, _hhmm_to_seconds("08:30"))

# 2. Same corridor, midday (less service)
show("direct corridor 13:00", o, d, _hhmm_to_seconds("13:00"))

# 3. Transfer-heavy Oshawa -> Whitby
o2 = router.stop_coords["100"]
d2 = router.stop_coords["1000"]
opts = show("transfer-heavy 08:30", o2, d2, _hhmm_to_seconds("08:30"))

# 4. Late evening (sparse service - should still find something or return 0 cleanly)
show("direct corridor 22:00", o, d, _hhmm_to_seconds("22:00"))

# 5. Unreachable-ish: middle of a rural area with no stops within 1200 m
show("nowhere (44.05, -78.9 -> 43.9, -79.0)", (44.05, -78.9), (43.9, -79.0),
     _hhmm_to_seconds("09:00"))
