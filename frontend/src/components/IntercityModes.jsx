"use client";

import { useState } from "react";
import { API_URL } from "../lib/config";

const PROVIDER_ICONS = {
  go_train: "🚆",
  via_rail: "🚄",
  megabus: "🚌",
  flixbus: "🚍",
  poparide: "🚗",
};

const PROVIDER_LABELS = {
  go_train: "GO Train",
  via_rail: "VIA Rail",
  megabus: "Megabus",
  flixbus: "FlixBus",
  poparide: "Poparide",
};

export default function IntercityModes({ planParams }) {
  const [options, setOptions] = useState(null);
  const [loading, setLoading] = useState(false);

  if (!planParams) return null;

  const fetchOptions = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/intercity`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          from_lat: planParams.from_lat,
          from_lon: planParams.from_lon,
          to_lat: planParams.to_lat,
          to_lon: planParams.to_lon,
        }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setOptions(data.options);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="">
      <button
        onClick={fetchOptions}
        disabled={loading}
        className="w-full bg-indigo-600 text-white text-sm py-1.5 rounded hover:bg-indigo-700 disabled:opacity-50"
      >
        {loading ? "Checking..." : "🚆 Long-Distance Options"}
      </button>

      {options && (
        <div className="mt-2 space-y-2">
          {options.filter((o) => o.available).length === 0 && (
            <div className="text-xs text-gray-500 p-2 bg-gray-50 rounded">
              No intercity options for this trip. Long-distance modes activate
              for trips over 40km (Toronto, Ottawa, Montreal, Kingston).
            </div>
          )}
          {options
            .filter((o) => o.available)
            .map((o) => (
              <div
                key={o.provider}
                className="border rounded-lg p-2.5 bg-white text-xs"
              >
                <div className="flex justify-between items-start">
                  <div>
                    <span className="text-base mr-1">
                      {PROVIDER_ICONS[o.provider]}
                    </span>
                    <span className="font-medium">
                      {PROVIDER_LABELS[o.provider]}
                    </span>
                    <div className="text-gray-500 mt-0.5">{o.summary}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold">{o.total_duration_min} min</div>
                    <div className="text-gray-700">${o.cost.toFixed(2)}</div>
                  </div>
                </div>

                <div className="mt-1.5 space-y-0.5 text-gray-600">
                  <div>📍 {o.first_mile}</div>
                  <div>🎫 {o.booking}</div>
                  {o.warnings.map((w, i) => (
                    <div key={i} className="text-amber-600">
                      ⚠ {w}
                    </div>
                  ))}
                </div>

                {o.url && (
                  <a
                    href={o.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1.5 inline-block text-indigo-600 hover:underline"
                  >
                    Book / check schedules →
                  </a>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
