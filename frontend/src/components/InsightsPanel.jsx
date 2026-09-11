"use client";

import { useState, useEffect } from "react";
import { API_URL } from "../lib/config";

const KIND_META = {
  time_value: { icon: "⏱️", label: "Time-Value" },
  fragility: { icon: "⚠️", label: "Reliability" },
  departure_window: { icon: "🕐", label: "Best Departure" },
  weekly_plan: { icon: "📅", label: "Weekly Plan" },
};

const CONDITION_ICONS = {
  clear: "☀️", rain: "🌧️", snow: "❄️", storm: "⛈️", unknown: "—",
};

export default function InsightsPanel({ planParams, monthlyBudget }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!planParams) return;
    const run = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_URL}/insights`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...planParams,
            monthly_budget: monthlyBudget || 0,
          }),
        });
        if (!res.ok) throw new Error(`${res.status}`);
        setData(await res.json());
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [planParams, monthlyBudget]);

  if (!planParams) return null;
  if (loading && !data) {
    return <div className="text-xs text-gray-500 p-2">Analyzing trip...</div>;
  }
  if (!data) return null;

  return (
    <div className="space-y-2">
      {data.insights.map((ins, i) => {
        const meta = KIND_META[ins.kind] || { icon: "💡", label: ins.kind };
        return (
          <div key={i} className="border rounded-lg p-2.5 bg-white text-xs">
            <div className="flex items-center gap-1.5 font-medium text-gray-800">
              <span>{meta.icon}</span>
              <span className="text-[10px] uppercase tracking-wide text-gray-500">
                {meta.label}
              </span>
            </div>
            <div className="font-semibold mt-1">{ins.headline}</div>
            <div className="text-gray-600 mt-0.5">{ins.detail}</div>

            {ins.kind === "departure_window" && ins.data.samples && (
              <div className="mt-2 flex gap-0.5 items-end h-12">
                {ins.data.samples.map((s) => {
                  const max = Math.max(
                    ...ins.data.samples.map((x) => x.duration_min)
                  );
                  const h = (s.duration_min / max) * 100;
                  const isBest = s.offset_min === ins.data.best_offset_min;
                  return (
                    <div
                      key={s.offset_min}
                      title={`${s.offset_min > 0 ? "+" : ""}${s.offset_min}min: ${s.duration_min}min trip`}
                      className={`flex-1 rounded-t ${
                        isBest ? "bg-green-500" : "bg-blue-300"
                      }`}
                      style={{ height: `${h}%` }}
                    />
                  );
                })}
              </div>
            )}
          </div>
        );
      })}

      {data.forecast?.length > 0 && (
        <div className="border rounded-lg p-2.5 bg-white text-xs">
          <div className="font-medium text-gray-800 mb-1">7-Day Outlook</div>
          <div className="flex justify-between">
            {data.forecast.map((d) => (
              <div key={d.date} className="text-center">
                <div className="text-[10px] text-gray-500">
                  {d.date.slice(5).replace("-", "/")}
                </div>
                <div>{CONDITION_ICONS[d.condition]}</div>
                <div className="text-[10px]">{d.temp_max_c?.toFixed(0)}°</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
