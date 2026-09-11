"use client";

export default function RouteCard({ option, selected, onClick }) {
  const rides = option.legs.filter((l) => l.mode === "transit");
  const walkLeg = option.legs.find((l) => l.mode === "walk");

  return (
    <div
      onClick={onClick}
      className={`p-3 rounded-lg border cursor-pointer transition-colors ${
        selected
          ? "border-blue-500 bg-blue-50 ring-1 ring-blue-500"
          : "border-gray-200 bg-white hover:border-gray-300"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-gray-900">
            {option.depart} → {option.arrive}
          </span>
          {selected && (
            <span className="text-xs bg-blue-600 text-white px-1.5 py-0.5 rounded">
              Selected
            </span>
          )}
        </div>
        <span className="text-sm text-gray-500">{option.duration_min} min</span>
      </div>

      <div className="flex items-center gap-3 text-xs text-gray-600 mb-2">
        <span className="flex items-center gap-1">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
          </svg>
          {option.transfers} transfer{option.transfers !== 1 ? "s" : ""}
        </span>
        {option.walk_m > 0 && (
          <span className="flex items-center gap-1">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            {option.walk_m}m walk
          </span>
        )}
      </div>

      <div className="space-y-1.5">
        {rides.map((leg, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <span className="bg-blue-100 text-blue-800 text-xs font-medium px-1.5 py-0.5 rounded min-w-[2rem] text-center">
              {leg.route_name}
            </span>
            <span className="text-gray-600 truncate flex-1">
              {leg.from_name.split("@")[0].trim()} → {leg.to_name.split("@")[0].trim()}
            </span>
            <span className="text-gray-400 text-xs">
              {leg.num_stops} stop{leg.num_stops !== 1 ? "s" : ""}
            </span>
          </div>
        ))}
        {walkLeg && walkLeg.distance_m > 10 && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span className="bg-gray-100 text-gray-600 text-xs font-medium px-1.5 py-0.5 rounded">
              Walk
            </span>
            <span>{walkLeg.distance_m}m to destination</span>
          </div>
        )}
      </div>
    </div>
  );
}