"""Profile startup phases to find the bottleneck."""
import time, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import date

t0 = time.time()
from router import TransitRouter
t1 = time.time()
print(f"import: {t1-t0:.1f}s")

r = TransitRouter()
t2 = time.time()
print(f"_load_static: {t2-t1:.1f}s")
print(f"  stops={len(r.stops)} trips={len(r.trip_route)} "
      f"stop_seq_trips={len(r.trip_stop_sequence)} shapes={len(r.shapes)}")

n = r.load_service_day(date.today())
t3 = time.time()
print(f"load_service_day: {t3-t1-t2:.1f}s -> {n} connections")
