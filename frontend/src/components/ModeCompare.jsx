"use client";

const MODE_ICONS = {
  transit: "🚌",
  drive: "🚗",
  cycle: "🚲",
  walk: "🚶",
  uber: "🚕",
  taxi: "🚖",
};

const MODE_LABELS = {
  transit: "DRT Bus",
  drive: "Drive",
  cycle: "Cycle",
  walk: "Walk",
  uber: "Uber",
  taxi: "Taxi",
};

const BADGE_COLORS = {
  Fastest: "bg-blue-100 text-blue-800",
  Cheapest: "bg-green-100 text-green-800",
  "Lowest CO2": "bg-emerald-100 text-emerald-800",
  "Most active": "bg-orange-100 text-orange-800",
};

export default function ModeCompare({ modes, recommended, delayRisk, onSelectMode }) {
  if (!modes || modes.length === 0) return null;

  return (
    <div className="space-y-2">
      {delayRisk > 0.2 && (
        <div className="text-xs bg-amber-50 border border-amber-200 text-amber-800 rounded px-2 py-1">
          Network delays elevated — transit reliability reduced
        </div>
      )}
      <div className="grid gap-2">
        {modes.map((m) => (
          <button
            key={m.mode}
            onClick={() => onSelectMode?.(m)}
            className={`text-left border rounded-lg p-3 transition-all hover:shadow-md ${
              m.mode === recommended
                ? "border-blue-500 bg-blue-50 ring-1 ring-blue-300"
                : "border-gray-200 bg-white hover:border-gray-300"
            } ${!m.available ? "opacity-50 cursor-not-allowed" : ""}`}
            disabled={!m.available}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <span className="text-lg">{MODE_ICONS[m.mode]}</span>
                <div>
                  <div className="font-medium text-sm">
                    {MODE_LABELS[m.mode]}
                    {m.mode === recommended && (
                      <span className="ml-2 text-xs text-blue-600 font-semibold">
                        Recommended
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500">{m.summary}</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm font-semibold">{m.duration_min} min</div>
                <div className="text-sm text-gray-700">
                  {m.cost === 0 ? "Free" : `$${m.cost.toFixed(2)}`}
                </div>
              </div>
            </div>

            {(m.badges.length > 0 || m.why.length > 0) && (
              <div className="mt-2 space-y-1">
                {m.badges.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {m.badges.map((b) => (
                      <span
                        key={b}
                        className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${BADGE_COLORS[b] || "bg-gray-100 text-gray-700"}`}
                      >
                        {b}
                      </span>
                    ))}
                  </div>
                )}
                <ul className="text-xs text-gray-600 space-y-0.5">
                  {m.why.map((w, i) => (
                    <li key={i}>• {w}</li>
                  ))}
                </ul>
                {m.warnings.length > 0 && (
                  <ul className="text-xs text-amber-600 space-y-0.5">
                    {m.warnings.map((w, i) => (
                      <li key={i}>⚠ {w}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            <div className="mt-2 flex gap-3 text-[10px] text-gray-500">
              <span>CO2: {m.co2_kg} kg</span>
              {m.calories > 0 && <span>Calories: {m.calories}</span>}
              <span>Score: {m.score}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
