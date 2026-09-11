import sqlite3
from datetime import date
from router import TransitRouter
from config import DB_PATH

r = TransitRouter()
key = "1199__201020_Timetable_-_2026-09"
seq = r.trip_stop_sequence.get(key)
print("stop_sequence for", key, "->", len(seq) if seq else "MISSING")

conn = sqlite3.connect(DB_PATH)
sid = conn.execute(
    "SELECT stop_id FROM stops WHERE stop_name='Dundas Eastbound @ White Oaks'"
).fetchone()
whitby = conn.execute(
    "SELECT stop_id FROM stops WHERE stop_name='Whitby Station'"
).fetchone()
conn.close()
print("White Oaks stop_id:", sid, "Whitby:", whitby)
if seq:
    print("White Oaks in seq:", sid[0] in seq if sid else None,
          "idx:", seq.index(sid[0]) if sid and sid[0] in seq else None)
    print("Whitby in seq:", whitby[0] in seq if whitby else None,
          "idx:", seq.index(whitby[0]) if whitby and whitby[0] in seq else None)
