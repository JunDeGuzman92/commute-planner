"use client";

import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "commute_planner_history";
const MAX_HISTORY = 20;

function load() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}

export function useTripHistory() {
  const [history, setHistory] = useState([]);

  useEffect(() => {
    setHistory(load());
  }, []);

  const record = useCallback((origin, destination, departAt, modesShown) => {
    setHistory((prev) => {
      const entry = {
        ts: Date.now(),
        weekday: new Date().getDay(),
        hour: departAt ? parseInt(departAt.split(":")[0]) : new Date().getHours(),
        origin: { lat: origin.lat, lon: origin.lon },
        destination: { lat: destination.lat, lon: destination.lon },
        depart_at: departAt,
        top_mode: modesShown?.[0] || null,
      };
      const next = [entry, ...prev.filter(
        (e) => !(
          Math.abs(e.origin.lat - origin.lat) < 0.001 &&
          Math.abs(e.destination.lat - destination.lat) < 0.001
        )
      )].slice(0, MAX_HISTORY);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch { /* quota — ignore */ }
      return next;
    });
  }, []);

  // Frequent OD pairs for quick-fill chips
  const frequent = history.reduce((acc, e) => {
    const key = `${e.origin.lat.toFixed(3)},${e.origin.lon.toFixed(3)}->` +
                `${e.destination.lat.toFixed(3)},${e.destination.lon.toFixed(3)}`;
    acc[key] = acc[key] || { ...e, count: 0 };
    acc[key].count++;
    return acc;
  }, {});
  const frequentTrips = Object.values(frequent)
    .sort((a, b) => b.count - a.count)
    .slice(0, 3);

  // Mode preference: what does the user usually end up with?
  const modeCounts = history.reduce((acc, e) => {
    if (e.top_mode) acc[e.top_mode] = (acc[e.top_mode] || 0) + 1;
    return acc;
  }, {});
  const preferredMode = Object.entries(modeCounts).sort(
    (a, b) => b[1] - a[1]
  )[0]?.[0] || null;

  return { history, record, frequentTrips, preferredMode };
}
