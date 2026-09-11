"""Intercity travel options from Durham Region.

No public real-time APIs exist for these, so we model scheduled services:
  - GO Transit (Lakeshore East rail + bus) — distance-based PRESTO fares
  - VIA Rail (Oshawa station, Toronto–Ottawa/Montreal corridor)
  - Megabus / FlixBus (Toronto departures — requires getting downtown first)
  - Poparide (carpool marketplace, per-seat pricing)

Each option reports door-to-door time (including the first/last mile),
cost, and booking friction so the commuter sees the real trade-offs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from router import haversine_m
from modes import _osrm_route, CAR_PER_KM, CO2_CAR

# --- GO Transit -----------------------------------------------------------
# Lakeshore East stations serving Durham (westbound towards Toronto Union)
GO_STATIONS = [
    {"name": "Oshawa GO", "lat": 43.8707, "lon": -78.8847, "fare_tier": 8},
    {"name": "Whitby GO", "lat": 43.8647, "lon": -78.9385, "fare_tier": 7},
    {"name": "Ajax GO", "lat": 43.8508, "lon": -79.0206, "fare_tier": 6},
    {"name": "Pickering GO", "lat": 43.8334, "lon": -79.0870, "fare_tier": 5},
]
UNION_STATION = {"name": "Union Station", "lat": 43.6453, "lon": -79.3806}

# Adult PRESTO fares to Union (15% PRESTO discount applied, 2026)
GO_FARES_PRESTO = {5: 9.10, 6: 10.25, 7: 11.20, 8: 12.40}
GO_TRAIN_MIN_PER_TIER = 9  # ~9 min per tier to Union from Lakeshore East
GO_HEADWAY_PEAK_MIN = 15   # trains every 15 min peak
GO_HEADWAY_OFFPEAK_MIN = 30

# --- VIA Rail (Oshawa station) --------------------------------------------
VIA_STATION = {"name": "Oshawa VIA", "lat": 43.8698, "lon": -78.8835}
# Corridor fares are dynamic; these are typical economy fares
VIA_FARES = {
    "toronto": 24.0, "ottawa": 89.0, "montreal": 99.0, "kingston": 62.0,
}
VIA_TIMES_MIN = {
    "toronto": 45, "ottawa": 240, "montreal": 300, "kingston": 130,
}

# --- Intercity buses (depart Toronto Union/Scarborough) -------------------
MEGABUS_BASE = 15.0   # Toronto–Kingston/Ottawa/Montreal promo fares
FLIXBUS_BASE = 12.0
BUS_BOOKING_NOTE = "Requires getting to Toronto departure point first"

# --- Poparide (carpool marketplace) ---------------------------------------
POPARIDE_PER_KM = 0.12      # typical per-seat rate
POPARIDE_BOOKING_FEE = 2.50
POPARIDE_MIN_FARE = 8.0


@dataclass
class IntercityOption:
    provider: str          # go_train | via_rail | megabus | flixbus | poparide
    available: bool
    summary: str
    total_duration_min: float = 0.0
    cost: float = 0.0
    co2_kg: float = 0.0
    first_mile: str = ""   # how to reach the departure point
    booking: str = ""      # how to book / board
    warnings: list[str] = field(default_factory=list)
    url: str | None = None


def _nearest_go_station(lat: float, lon: float) -> dict:
    return min(GO_STATIONS,
               key=lambda s: haversine_m(lat, lon, s["lat"], s["lon"]))


def go_train_option(from_lat: float, from_lon: float, to_lat: float,
                    to_lon: float, drive_min_to_station: float | None = None
                    ) -> IntercityOption:
    """GO train: drive/DRT to station → train to Union → local Toronto trip.

    Only relevant when the destination is near Toronto. We check if the
    destination is meaningfully closer to Union than to the origin.
    """
    dest_to_union_km = haversine_m(to_lat, to_lon, UNION_STATION["lat"],
                                   UNION_STATION["lon"]) / 1000
    origin_to_union_km = haversine_m(from_lat, from_lon, UNION_STATION["lat"],
                                     UNION_STATION["lon"]) / 1000

    if dest_to_union_km > 40:  # destination not in Toronto area
        return IntercityOption("go_train", False, "GO Train",
                               warnings=["Destination outside GO service area"])

    station = _nearest_go_station(from_lat, from_lon)
    access_km = haversine_m(from_lat, from_lon, station["lat"],
                            station["lon"]) / 1000
    # First mile: drive to station (GO parking is free) unless very close
    access_min = drive_min_to_station if drive_min_to_station else max(
        5, access_km / 30 * 60)
    train_min = GO_TRAIN_MIN_PER_TIER * station["fare_tier"]
    wait_min = GO_HEADWAY_PEAK_MIN / 2  # average wait
    egress_min = dest_to_union_km / 4.5 * 60  # TTC/walk from Union

    total = access_min + wait_min + train_min + egress_min
    fare = GO_FARES_PRESTO[station["fare_tier"]]
    # One Fare: DRT leg is free if user takes DRT to the station
    train_km = haversine_m(station["lat"], station["lon"],
                           UNION_STATION["lat"], UNION_STATION["lon"]) / 1000

    return IntercityOption(
        provider="go_train",
        available=True,
        summary=f"GO Train from {station['name']} to Union",
        total_duration_min=round(total),
        cost=round(fare, 2),
        co2_kg=round(train_km * 0.041, 2),  # electrified Lakeshore line
        first_mile=f"{access_min:.0f} min to {station['name']} "
                   f"(DRT free w/ One Fare, or drive — parking free)",
        booking="Tap PRESTO on/off",
        warnings=[f"Trains every {GO_HEADWAY_PEAK_MIN}-{GO_HEADWAY_OFFPEAK_MIN} min"],
        url="https://www.gotransit.com/en/plan-your-trip",
    )


def via_rail_option(from_lat: float, from_lon: float, to_lat: float,
                    to_lon: float) -> IntercityOption:
    """VIA Rail from Oshawa — only sensible for long intercity trips."""
    access_km = haversine_m(from_lat, from_lon, VIA_STATION["lat"],
                            VIA_STATION["lon"]) / 1000
    # Heuristic: destination beyond 100 km suggests intercity
    trip_km = haversine_m(from_lat, from_lon, to_lat, to_lon) / 1000
    if trip_km < 60:
        return IntercityOption("via_rail", False, "VIA Rail",
                               warnings=["VIA is for intercity trips (60+ km)"])

    # Match destination to nearest corridor city
    dests = {
        "toronto": (43.6453, -79.3806), "ottawa": (45.4215, -75.6972),
        "montreal": (45.5019, -73.5674), "kingston": (44.2312, -76.4860),
    }
    nearest = min(dests.items(),
                  key=lambda kv: haversine_m(to_lat, to_lon, *kv[1]))
    city, (clat, clon) = nearest
    if haversine_m(to_lat, to_lon, clat, clon) / 1000 > 50:
        return IntercityOption("via_rail", False, "VIA Rail",
                               warnings=["Destination not near VIA corridor"])

    access_min = max(10, access_km / 30 * 60)
    total = access_min + VIA_TIMES_MIN[city] + 15  # +arrival buffer
    return IntercityOption(
        provider="via_rail",
        available=True,
        summary=f"VIA Rail Oshawa → {city.title()}",
        total_duration_min=round(total),
        cost=VIA_FARES[city],
        co2_kg=round(haversine_m(VIA_STATION["lat"], VIA_STATION["lon"],
                                 clat, clon) / 1000 * 0.045, 2),
        first_mile=f"{access_min:.0f} min to Oshawa VIA station",
        booking="Book in advance at viarail.ca — economy fares sell out",
        warnings=["Advance purchase strongly recommended"],
        url="https://www.viarail.ca",
    )


def intercity_bus_option(from_lat: float, from_lon: float, to_lat: float,
                         to_lon: float) -> list[IntercityOption]:
    """Megabus / FlixBus from Toronto — cheap but requires reaching Toronto."""
    trip_km = haversine_m(from_lat, from_lon, to_lat, to_lon) / 1000
    if trip_km < 100:
        return []  # not worth it for short trips

    # Getting to Toronto Union Bus Terminal
    to_toronto = _osrm_route("driving", from_lat, from_lon,
                             UNION_STATION["lat"], UNION_STATION["lon"])
    access_min = (to_toronto["duration_s"] / 60) if to_toronto else 60

    # Rough intercity time by road at 85 km/h effective
    bus_min = trip_km / 85 * 60 + 30
    total = access_min + bus_min + 20  # +terminal wait

    return [
        IntercityOption(
            provider="megabus",
            available=True,
            summary=f"Megabus from Toronto (~{trip_km:.0f} km)",
            total_duration_min=round(total),
            cost=round(MEGABUS_BASE + trip_km * 0.09, 2),
            co2_kg=round(trip_km * 0.03, 2),
            first_mile=f"{access_min:.0f} min to Toronto bus terminal",
            booking="Book at megabus.com — promo fares from $15",
            warnings=[BUS_BOOKING_NOTE, "Promo fares are non-refundable"],
            url="https://ca.megabus.com",
        ),
        IntercityOption(
            provider="flixbus",
            available=True,
            summary=f"FlixBus from Toronto (~{trip_km:.0f} km)",
            total_duration_min=round(total),
            cost=round(FLIXBUS_BASE + trip_km * 0.085, 2),
            co2_kg=round(trip_km * 0.03, 2),
            first_mile=f"{access_min:.0f} min to Toronto bus terminal",
            booking="Book at flixbus.ca",
            warnings=[BUS_BOOKING_NOTE],
            url="https://www.flixbus.ca",
        ),
    ]


def poparide_option(from_lat: float, from_lon: float, to_lat: float,
                    to_lon: float) -> IntercityOption:
    """Poparide carpool — per-seat pricing, good for 40-300 km trips."""
    trip_km = haversine_m(from_lat, from_lon, to_lat, to_lon) / 1000
    if not (25 <= trip_km <= 400):
        return IntercityOption("poparide", False, "Poparide",
                               warnings=["Poparide suits 25–400 km trips"])

    r = _osrm_route("driving", from_lat, from_lon, to_lat, to_lon)
    drive_min = (r["duration_s"] / 60) if r else trip_km / 80 * 60
    cost = max(POPARIDE_MIN_FARE,
               trip_km * POPARIDE_PER_KM + POPARIDE_BOOKING_FEE)
    return IntercityOption(
        provider="poparide",
        available=True,
        summary=f"Poparide carpool ({trip_km:.0f} km)",
        total_duration_min=round(drive_min + 10),  # +meet-up buffer
        cost=round(cost, 2),
        co2_kg=round(trip_km * CO2_CAR / 2, 2),  # shared ride halves CO2
        first_mile="Meet driver at agreed pickup point",
        booking="Book a seat in the Poparide app",
        warnings=["Availability depends on posted trips — check app",
                  "Not a scheduled service"],
        url="https://www.poparide.com",
    )


def intercity_options(from_lat: float, from_lon: float, to_lat: float,
                      to_lon: float) -> list[IntercityOption]:
    """All applicable intercity options for this trip."""
    opts = [
        go_train_option(from_lat, from_lon, to_lat, to_lon),
        via_rail_option(from_lat, from_lon, to_lat, to_lon),
        poparide_option(from_lat, from_lon, to_lat, to_lon),
    ]
    opts.extend(intercity_bus_option(from_lat, from_lon, to_lat, to_lon))
    return opts
