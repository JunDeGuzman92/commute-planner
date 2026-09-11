"use client";

import { useState } from "react";
import { API_URL } from "../lib/config";

export default function BudgetPanel({ planParams }) {
  const [budget, setBudget] = useState(200);
  const [trips, setTrips] = useState(10);
  const [savings, setSavings] = useState(0);
  const [co2Cap, setCo2Cap] = useState(0);
  const [foodInsecure, setFoodInsecure] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  if (!planParams) return null;

  const run = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/budget`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...planParams,
          monthly_budget: parseFloat(budget),
          trips_per_week: parseInt(trips),
          savings_balance: parseFloat(savings),
          food_insecure: foodInsecure,
          co2_cap_kg: parseFloat(co2Cap) || 0,
        }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setResult(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">
        💰 Transport Budget
      </h3>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <label className="flex flex-col">
          <span className="text-gray-600">Monthly budget ($)</span>
          <input
            type="number"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-gray-600">Trips per week</span>
          <input
            type="number"
            value={trips}
            onChange={(e) => setTrips(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-gray-600">Current savings ($)</span>
          <input
            type="number"
            value={savings}
            onChange={(e) => setSavings(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-gray-600">CO2 cap (kg/mo, 0=off)</span>
          <input
            type="number"
            value={co2Cap}
            onChange={(e) => setCo2Cap(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </label>
        <label className="flex items-end gap-1 pb-1">
          <input
            type="checkbox"
            checked={foodInsecure}
            onChange={(e) => setFoodInsecure(e.target.checked)}
          />
          <span className="text-gray-600">Food budget is tight</span>
        </label>
      </div>

      <button
        onClick={run}
        disabled={loading}
        className="mt-2 w-full bg-green-600 text-white text-sm py-1.5 rounded hover:bg-green-700 disabled:opacity-50"
      >
        {loading ? "Analyzing..." : "Analyze Budget"}
      </button>

      {result && (
        <div className="mt-3 space-y-2 text-xs">
          <div className="bg-gray-50 rounded p-2 border">
            <div className="font-semibold text-gray-800">
              {result.advisor.headline}
            </div>
            <div className="text-gray-600 mt-1">
              Spend ${result.budget_state.monthly_spend}/mo of $
              {result.budget_state.monthly_budget} (
              {result.budget_state.trips_per_month} trips)
            </div>
            {result.budget_state.co2_cap_kg > 0 && (
              <div className="mt-1.5">
                <div className="flex justify-between text-[10px] text-gray-500">
                  <span>Carbon budget</span>
                  <span>
                    {result.budget_state.monthly_co2} /{" "}
                    {result.budget_state.co2_cap_kg} kg CO2
                  </span>
                </div>
                <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden mt-0.5">
                  <div
                    className={`h-full rounded-full ${
                      result.budget_state.monthly_co2 >
                      result.budget_state.co2_cap_kg
                        ? "bg-red-500"
                        : "bg-emerald-500"
                    }`}
                    style={{
                      width: `${Math.min(
                        100,
                        (result.budget_state.monthly_co2 /
                          result.budget_state.co2_cap_kg) *
                          100
                      )}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>

          <div>
            <div className="font-medium text-gray-700 mb-1">Recommended actions:</div>
            <ul className="space-y-1 text-gray-600">
              {result.advisor.actions.map((a, i) => (
                <li key={i}>• {a}</li>
              ))}
            </ul>
          </div>

          {Object.keys(result.advisor.suggested_allocation).length > 0 && (
            <div>
              <div className="font-medium text-gray-700 mb-1">
                Suggested allocation:
              </div>
              {Object.entries(result.advisor.suggested_allocation).map(
                ([k, v]) => (
                  <div key={k} className="flex justify-between text-gray-600">
                    <span className="capitalize">{k.replace("_", " ")}</span>
                    <span>${v}</span>
                  </div>
                )
              )}
            </div>
          )}

          <div>
            <div className="font-medium text-gray-700 mb-1">
              All modes vs your budget:
            </div>
            {result.comparison.modes.map((m) => (
              <div
                key={m.mode}
                className={`flex justify-between ${
                  m.within_budget ? "text-gray-600" : "text-red-600"
                }`}
              >
                <span>
                  {m.mode} {m.mode === result.recommended_mode && "⭐"}
                </span>
                <span>
                  ${m.monthly_cost}/mo{" "}
                  {!m.within_budget && `(over by $${-m.budget_delta})`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
