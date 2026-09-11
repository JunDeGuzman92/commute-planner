"use client";

import { useState, useEffect, useRef } from "react";
import { API_URL } from "../lib/config";

const MODE_ICONS = {
  transit: "🚌", drive: "🚗", cycle: "🚲", walk: "🚶", uber: "🚕", taxi: "🚖",
};

export function DisruptionBanner({ routes }) {
  const [disruptions, setDisruptions] = useState([]);

  useEffect(() => {
    if (!routes || routes.length === 0) return;
    const names = [
      ...new Set(
        routes.flatMap((r) =>
          r.legs.filter((l) => l.route_name).map((l) => l.route_name)
        )
      ),
    ].join(",");
    if (!names) return;

    const check = async () => {
      try {
        const res = await fetch(
          `${API_URL}/disruptions?routes=${encodeURIComponent(names)}&threshold_min=5`
        );
        const data = await res.json();
        setDisruptions(data.disruptions || []);
      } catch { /* silent */ }
    };
    check();
    const id = setInterval(check, 60000);
    return () => clearInterval(id);
  }, [routes]);

  if (disruptions.length === 0) return null;

  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-2 text-xs">
      <div className="font-semibold text-red-800">
        ⚠ Live disruptions on your route
      </div>
      {disruptions.map((d) => (
        <div key={d.trip_id} className="text-red-700 mt-0.5">
          {d.route} {d.headsign && `(${d.headsign})`}: +{d.delay_min} min
        </div>
      ))}
    </div>
  );
}

export function LeaveNowButton({ route }) {
  const [permState, setPermState] = useState("default");
  const [scheduled, setScheduled] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => {
    if ("Notification" in window) setPermState(Notification.permission);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, []);

  if (!route) return null;

  const firstTransit = route.legs.find((l) => l.mode === "transit");
  if (!firstTransit) return null;

  const schedule = async () => {
    if (!("Notification" in window)) return;
    let perm = Notification.permission;
    if (perm === "default") {
      perm = await Notification.requestPermission();
      setPermState(perm);
    }
    if (perm !== "granted") return;

    // Parse "HH:MM" board time, leave 8 min before
    const [h, m] = firstTransit.depart.split(":").map(Number);
    const now = new Date();
    const target = new Date(now);
    target.setHours(h, m - 8, 0, 0);
    if (target <= now) {
      alert("That departure is in the past — pick a later route.");
      return;
    }
    const ms = target - now;
    timerRef.current = setTimeout(() => {
      new Notification("Time to leave!", {
        body: `Leave now to catch the ${firstTransit.route_name} at ${firstTransit.depart} from ${firstTransit.from_name}`,
        icon: "/favicon.ico",
      });
      setScheduled(null);
    }, ms);
    setScheduled(target);
  };

  if (scheduled) {
    return (
      <button
        onClick={() => { clearTimeout(timerRef.current); setScheduled(null); }}
        className="w-full text-xs bg-emerald-100 text-emerald-800 border border-emerald-300 rounded py-1.5"
      >
        ✓ Reminder set for {scheduled.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} — tap to cancel
      </button>
    );
  }

  return (
    <button
      onClick={schedule}
      disabled={permState === "denied"}
      className="w-full text-xs bg-blue-100 text-blue-800 border border-blue-300 rounded py-1.5 hover:bg-blue-200 disabled:opacity-50"
    >
      🔔 Notify me when it's time to leave (8 min before {firstTransit.depart} bus)
    </button>
  );
}
