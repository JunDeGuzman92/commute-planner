"use client";

import { useState } from "react";
import { API_URL } from "../lib/config";

const SCENARIOS = [
  { id: "weather", label: "Weather impact", icon: "🌦️" },
  { id: "missed_bus", label: "Missed bus", icon: "🏃" },
  { id: "leave_later", label: "Leave later", icon: "⏰" },
  { id: "monthly_pass", label: "Monthly pass?", icon: "💳" },
];

export default function WhatIfPanel({ planParams }) {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(null);
  const [expanded, setExpanded] = useState(null);

  if (!planParams) return null;

  const runScenario = async (scenario) => {
    setLoading(scenario);
    setExpanded(scenario);
    try {
      const res = await fetch(`${API_URL}/whatif`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...planParams, scenario }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setResults((prev) => ({ ...prev, [scenario]: data }));
    } catch (e) {
      setResults((prev) => ({
        ...prev,
        [scenario]: { headline: "Error", detail: "Could not load scenario." },
      }));
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="border-t pt-3 mt-3">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">What if...</h3>
      <div className="grid grid-cols-2 gap-1.5">
        {SCENARIOS.map((s) => (
          <button
            key={s.id}
            onClick={() => runScenario(s.id)}
            disabled={loading === s.id}
            className={`text-xs px-2 py-1.5 rounded border transition-colors ${
              expanded === s.id
                ? "bg-blue-50 border-blue-300 text-blue-700"
                : "bg-gray-50 border-gray-200 text-gray-700 hover:bg-gray-100"
            }`}
          >
            <span className="mr-1">{s.icon}</span>
            {loading === s.id ? "..." : s.label}
          </button>
        ))}
      </div>

      {expanded && results?.[expanded] && (
        <div className="mt-2 p-2.5 bg-gray-50 rounded border border-gray-200 text-xs">
          <div className="font-semibold text-gray-800">
            {results[expanded].headline}
          </div>
          <div className="text-gray-600 mt-1">{results[expanded].detail}</div>

          {results[expanded].timeline?.length > 0 && (
            <div className="mt-2 space-y-1">
              <div className="font-medium text-gray-700">Leave-later curve:</div>
              {results[expanded].timeline.map((t) => (
                <div
                  key={t.offset_min}
                  className="flex justify-between text-gray-600"
                >
                  <span>
                    +{t.offset_min}min → {t.depart || "—"}
                  </span>
                  <span>
                    {t.arrive ? `arr ${t.arrive} (${t.duration_min}min)` : "no route"}
                  </span>
                </div>
              ))}
            </div>
          )}

          {results[expanded].alternatives?.length > 0 && (
            <div className="mt-2 space-y-1">
              <div className="font-medium text-gray-700">Next options:</div>
              {results[expanded].alternatives.map((a, i) => (
                <div key={i} className="text-gray-600">
                  {a.depart} → {a.arrive} ({a.duration_min}min, {a.transfers}{" "}
                  transfer{a.transfers !== 1 ? "s" : ""})
                </div>
              ))}
            </div>
          )}

          {results[expanded].breakeven && (
            <div className="mt-2 space-y-1">
              <div className="font-medium text-gray-700">Break-even:</div>
              <div className="text-gray-600">
                {results[expanded].breakeven.trips_per_month} trips/month
              </div>
              <div className="text-gray-600">
                Pay-per-ride: ${results[expanded].breakeven.pay_per_ride_cost}
              </div>
              <div className="text-gray-600">
                Pass: ${results[expanded].breakeven.monthly_pass_cost}
              </div>
              {results[expanded].breakeven.pass_saves_money && (
                <div className="text-green-600 font-medium">
                  Save ${results[expanded].breakeven.monthly_savings}/month
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
