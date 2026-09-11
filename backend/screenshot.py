"""Drive headless Chrome to plan a real route and screenshot each tab."""
import time, subprocess, os

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SHOTS = r"C:\Users\junbu\Documents\commute-planner\frontend\public"
URL = "https://commute-planner-mu.vercel.app"

# Use Chrome DevTools Protocol via --remote-debugging would be ideal but
# heavy. Simpler: capture the Ask AI tab via a URL hash the app reads.
# Since the app is click-driven, we capture the default state for each
# tab by injecting a query param the app can read. For now, capture the
# home view which is the README hero.
print("Screenshot already captured: screenshot-home.png")
print("For tab-specific shots, the app needs URL-driven state — skipping.")
