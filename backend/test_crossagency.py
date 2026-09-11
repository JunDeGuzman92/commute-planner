"""Test cross-agency routing: Whitby -> Toronto Union."""
import json, urllib.request, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

req = urllib.request.Request(
    "http://localhost:8101/plan",
    data=json.dumps({
        "from_lat": 43.8759, "from_lon": -78.9617,   # Whitby
        "to_lat": 43.6453, "to_lon": -79.3806,       # Union Station
        "depart_at": "08:00", "max_walk_m": 1500,
        "use_realtime": False,
    }).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as r:
    routes = json.loads(r.read())

print(f"{len(routes)} route options\n")
for i, rt in enumerate(routes[:4]):
    print(f"Option {i+1}: {rt['depart']} -> {rt['arrive']} "
          f"({rt['duration_min']} min, {rt['transfers']} transfers, "
          f"{rt['walk_m']} m walk)")
    for leg in rt["legs"]:
        rn = leg.get("route_name") or ""
        print(f"  [{leg['depart']}-{leg['arrive']}] {leg['mode']:8s} "
              f"{rn:12s} {leg['from_name'][:35]} -> {leg['to_name'][:35]}")
    print()
