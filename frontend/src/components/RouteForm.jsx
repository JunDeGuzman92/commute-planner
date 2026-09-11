"use client";

import { useState } from "react";

export default function RouteForm({
  origin,
  destination,
  onPlan,
  loading,
  onOriginChange,
  onDestinationChange,
}) {
  const [departAt, setDepartAt] = useState("08:30");
  const [maxWalk, setMaxWalk] = useState(1200);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!origin || !destination) {
      alert("Please set both origin and destination on the map");
      return;
    }
    onPlan({
      from_lat: origin.lat,
      from_lon: origin.lon,
      to_lat: destination.lat,
      to_lon: destination.lon,
      depart_at: departAt,
      max_walk_m: maxWalk,
      use_realtime: true,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Depart after
        </label>
        <input
          type="time"
          value={departAt}
          onChange={(e) => setDepartAt(e.target.value)}
          className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Max walking distance: {maxWalk}m
        </label>
        <input
          type="range"
          min="200"
          max="2500"
          step="100"
          value={maxWalk}
          onChange={(e) => setMaxWalk(Number(e.target.value))}
          className="w-full"
        />
      </div>

      <button
        type="submit"
        disabled={loading || !origin || !destination}
        className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
      >
        {loading ? "Planning..." : "Find Routes"}
      </button>

      <p className="text-xs text-gray-500">
        Click "Set Origin" or "Set Destination" then click on the map to choose locations.
      </p>
    </form>
  );
}