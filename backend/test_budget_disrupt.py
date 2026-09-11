"""Test budget CO2 cap + disruptions endpoint."""
import json, urllib.request, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8101"

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

# 1. Budget with CO2 cap breach (driver with tight carbon cap)
r = post("/budget", {
    "from_lat": 43.8759, "from_lon": -78.9617,
    "to_lat": 43.8727, "to_lon": -78.8554,
    "depart_at": "08:30", "monthly_budget": 800, "trips_per_week": 10,
    "profile": "fastest", "co2_cap_kg": 30,
})
print("BUDGET (driver, 30kg CO2 cap):")
print(f"  Mode: {r['recommended_mode']}, CO2/mo: {r['budget_state']['monthly_co2']} kg")
print(f"  {r['advisor']['headline']}")
for a in r["advisor"]["actions"]:
    print(f"   - {a}")

# 2. Disruptions
req = urllib.request.Request(BASE + "/disruptions?routes=301,917,403,LE&threshold_min=5")
with urllib.request.urlopen(req, timeout=30) as resp:
    d = json.loads(resp.read())
print(f"\nDISRUPTIONS (watching 301/917/403/LE):")
print(f"  Network delay risk: {d['network_delay_risk']}")
print(f"  Flagged trips: {len(d['disruptions'])}")
for p in d["disruptions"][:3]:
    print(f"   - {p['route']} {p['headsign']}: +{p['delay_min']} min")
