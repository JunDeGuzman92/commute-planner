import json, urllib.request, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://commute-planner-production.up.railway.app"
COMMON = {
    "from_lat": 43.8759, "from_lon": -78.9617,
    "to_lat": 43.8727, "to_lon": -78.8554,
    "depart_at": "08:30",
}

def post(path, payload):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

messages = [
    "what's the cheapest way to get there",
    "when should I leave",
    "is the monthly pass worth it",
    "how do I get to Ottawa",
    "is this route reliable",
    "plan my week",
    "what if it rains",
    "can I afford uber every day on $300",
    "hello",
]

for msg in messages:
    payload = dict(COMMON)
    payload["message"] = msg
    if "ottawa" in msg.lower():
        payload["to_lat"], payload["to_lon"] = 45.4215, -75.6972
    r = post("/chat", payload)
    print(f"Q: {msg}")
    print(f"   [{r.get('intent')}] {r.get('reply', '')[:220]}")
    print()
