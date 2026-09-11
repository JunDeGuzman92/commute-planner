"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import RouteForm from "../components/RouteForm";
import { API_URL } from "../lib/config";
import RouteCard from "../components/RouteCard";
import ModeCompare from "../components/ModeCompare";
import WhatIfPanel from "../components/WhatIfPanel";
import BudgetPanel from "../components/BudgetPanel";
import IntercityModes from "../components/IntercityModes";
import InsightsPanel from "../components/InsightsPanel";
import ChatPanel from "../components/ChatPanel";
import { DisruptionBanner, LeaveNowButton } from "../components/TripTools";
import { useTripHistory } from "../lib/useTripHistory";
import InstallPrompt from "../components/InstallPrompt";

mapboxgl.accessToken = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || "";

export default function HomePage() {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [origin, setOrigin] = useState(null);
  const [destination, setDestination] = useState(null);
  const [routes, setRoutes] = useState([]);
  const [selectedRoute, setSelectedRoute] = useState(null);
  const [loading, setLoading] = useState(false);
  const [clickMode, setClickMode] = useState(null);
  const [markers, setMarkers] = useState({ origin: null, destination: null });
  const [routeLines, setRouteLines] = useState([]);
  const [stopMarkers, setStopMarkers] = useState([]);
  const [vehicleMarkers, setVehicleMarkers] = useState([]);
  const [showVehicles, setShowVehicles] = useState(false);
  const [compareData, setCompareData] = useState(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [planParams, setPlanParams] = useState(null);
  const [activeTab, setActiveTab] = useState("trip");
  const { record, frequentTrips } = useTripHistory();
  // Bottom sheet on mobile: "peek" | "half" | "full"
  const [sheet, setSheet] = useState("half");
  const touchStartY = useRef(null);

  useEffect(() => {
    // React 19 strict mode: effects run mount → cleanup → mount.
    // Only init when container exists and map not already created.
    if (!mapContainer.current || map.current) return;

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: "mapbox://styles/mapbox/streets-v12",
      center: [-78.94, 43.89],
      zoom: 11,
    });

    map.current.on("load", () => {
      setMapLoaded(true);
    });

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
        setMapLoaded(false);
      }
    };
  }, []);

  useEffect(() => {
    if (!map.current || !mapLoaded) return;

    const handleClick = (e) => {
      const { lng, lat } = e.lngLat;

      if (clickMode === "origin") {
        setOrigin({ lat, lon: lng });
        addMarker("origin", lng, lat);
        setClickMode(null);
      } else if (clickMode === "destination") {
        setDestination({ lat, lon: lng });
        addMarker("destination", lng, lat);
        setClickMode(null);
      }
    };

    map.current.on("click", handleClick);
    return () => {
      if (map.current) map.current.off("click", handleClick);
    };
  }, [mapLoaded, clickMode, markers]);

  const addMarker = (type, lng, lat) => {
    if (markers[type]) {
      markers[type].remove();
    }

    const el = document.createElement("div");
    el.style.width = "24px";
    el.style.height = "24px";
    el.style.borderRadius = "50%";
    el.style.backgroundColor = type === "origin" ? "#22c55e" : "#ef4444";
    el.style.border = "3px solid white";
    el.style.boxShadow = "0 2px 4px rgba(0,0,0,0.3)";

    const marker = new mapboxgl.Marker(el)
      .setLngLat([lng, lat])
      .addTo(map.current);

    setMarkers((prev) => ({ ...prev, [type]: marker }));
  };

  const clearRouteLines = useCallback(() => {
    routeLines.forEach((id) => {
      if (map.current.getLayer(id)) map.current.removeLayer(id);
      if (map.current.getSource(id)) map.current.removeSource(id);
    });
    setRouteLines([]);
    // Clear stop markers
    stopMarkers.forEach((m) => m.remove());
    setStopMarkers([]);
  }, [routeLines, stopMarkers]);

  const addStopMarker = useCallback((lng, lat, label, color) => {
    if (!map.current) return null;
    const el = document.createElement("div");
    el.style.width = "16px";
    el.style.height = "16px";
    el.style.borderRadius = "50%";
    el.style.backgroundColor = color;
    el.style.border = "2px solid white";
    el.style.boxShadow = "0 1px 3px rgba(0,0,0,0.3)";
    el.title = label;
    const marker = new mapboxgl.Marker(el).setLngLat([lng, lat]).addTo(map.current);
    setStopMarkers((prev) => [...prev, marker]);
    return marker;
  }, []);

  const drawRoute = useCallback(
    (routeOption) => {
      if (!map.current || !mapLoaded) return;

      clearRouteLines();
      const newLineIds = [];
      const allCoords = [];

      routeOption.legs.forEach((leg, idx) => {
        // Add boarding stop marker
        if (leg.from_lat && leg.from_lon) {
          addStopMarker(leg.from_lon, leg.from_lat, `Board: ${leg.from_name}`, "#3b82f6");
        }
        // Add alighting stop marker
        if (leg.to_lat && leg.to_lon) {
          addStopMarker(leg.to_lon, leg.to_lat, `Alight: ${leg.to_name}`, "#8b5cf6");
        }

        if (leg.mode !== "transit" || !leg.geometry) return;

        const sourceId = `route-${idx}-${Date.now()}`;
        const layerId = `route-${idx}-${Date.now()}`;

        map.current.addSource(sourceId, {
          type: "geojson",
          data: {
            type: "Feature",
            properties: { route_name: leg.route_name },
            geometry: leg.geometry,
          },
        });

        map.current.addLayer({
          id: layerId,
          type: "line",
          source: sourceId,
          layout: {
            "line-join": "round",
            "line-cap": "round",
          },
          paint: {
            "line-color": `hsl(${(idx * 137) % 360}, 70%, 50%)`,
            "line-width": 5,
            "line-opacity": 0.9,
          },
        });

        // Add route label at midpoint
        const midIdx = Math.floor(leg.geometry.coordinates.length / 2);
        const midCoord = leg.geometry.coordinates[midIdx];
        if (midCoord) {
          const labelId = `label-${idx}-${Date.now()}`;
          map.current.addSource(labelId, {
            type: "geojson",
            data: {
              type: "Feature",
              properties: { route_name: leg.route_name },
              geometry: { type: "Point", coordinates: midCoord },
            },
          });
          map.current.addLayer({
            id: labelId,
            type: "symbol",
            source: labelId,
            layout: {
              "text-field": ["get", "route_name"],
              "text-size": 12,
              "text-font": ["Open Sans Bold"],
            },
            paint: {
              "text-color": "#fff",
              "text-halo-color": `hsl(${(idx * 137) % 360}, 70%, 40%)`,
              "text-halo-width": 2,
            },
          });
          newLineIds.push(labelId);
        }

        newLineIds.push(sourceId);
        allCoords.push(...leg.geometry.coordinates);
      });

      // Fit map to show entire route
      if (allCoords.length > 0) {
        const bounds = allCoords.reduce(
          (bounds, coord) => bounds.extend(coord),
          new mapboxgl.LngLatBounds(allCoords[0], allCoords[0])
        );
        // Desktop has a 384px left panel; pad the bounds so the route
        // centers in the visible map area, not behind the panel.
        const isDesktop = window.matchMedia("(min-width: 768px)").matches;
        map.current.fitBounds(bounds, {
          padding: isDesktop
            ? { top: 50, bottom: 50, left: 434, right: 50 }
            : { top: 60, bottom: 260, left: 30, right: 30 },
        });
      }

      setRouteLines(newLineIds);
    },
    [mapLoaded, clearRouteLines]
  );

  const handlePlan = async (planData) => {
    setLoading(true);
    setPlanParams(planData);
    try {
      const res = await fetch(`${API_URL}/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(planData),
      });
      const data = await res.json();
      setRoutes(data);
      if (data.length > 0) {
        setSelectedRoute(0);
        drawRoute(data[0]);
        // Record the trip for pattern learning (quick-fill chips)
        record(
          { lat: planData.from_lat, lon: planData.from_lon },
          { lat: planData.to_lat, lon: planData.to_lon },
          planData.depart_at,
          data[0] ? ["transit"] : null
        );
      }
    } catch (e) {
      console.error("Plan failed:", e);
      alert("Failed to plan route. Is the backend running on port 8101?");
    } finally {
      setLoading(false);
    }
  };

  const handleCompare = async () => {
    if (!planParams) return;
    setCompareLoading(true);
    try {
      const res = await fetch(`${API_URL}/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(planParams),
      });
      const data = await res.json();
      setCompareData(data);
    } catch (e) {
      console.error("Compare failed:", e);
    } finally {
      setCompareLoading(false);
    }
  };

  // Redraw when selection changes
  useEffect(() => {
    if (selectedRoute !== null && routes[selectedRoute]) {
      drawRoute(routes[selectedRoute]);
    }
  }, [selectedRoute, routes, drawRoute]);

  // Poll live vehicles
  useEffect(() => {
    if (!mapLoaded || !showVehicles) return;

    const fetchVehicles = async () => {
      try {
        const res = await fetch(`${API_URL}/vehicles`);
        const data = await res.json();

        // Clear old vehicle markers
        vehicleMarkers.forEach((m) => m.remove());
        const newMarkers = [];

        data.forEach((v) => {
          const el = document.createElement("div");
          el.style.width = "12px";
          el.style.height = "12px";
          el.style.borderRadius = "50%";
          el.style.backgroundColor = "#f59e0b";
          el.style.border = "2px solid white";
          el.style.boxShadow = "0 1px 2px rgba(0,0,0,0.3)";
          el.title = `Bus ${v.vehicle_id}`;

          const marker = new mapboxgl.Marker(el)
            .setLngLat([v.lon, v.lat])
            .addTo(map.current);
          newMarkers.push(marker);
        });

        setVehicleMarkers(newMarkers);
      } catch (e) {
        console.error("Failed to fetch vehicles:", e);
      }
    };

    fetchVehicles();
    const interval = setInterval(fetchVehicles, 30000);
    return () => clearInterval(interval);
  }, [mapLoaded, showVehicles, vehicleMarkers]);

  // --- shared sidebar/sheet content (rendered once, used in both layouts) ---
  const plannerContent = (
    <>
      {/* Tab bar */}
      <div className="flex border-b bg-white text-[11px] md:text-xs font-medium sticky top-0 z-10">
        {[
          ["trip", "Trip"],
          ["insights", "Insights"],
          ["budget", "Budget"],
          ["ask", "Ask AI"],
        ].map(([id, label]) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`flex-1 min-w-0 py-2.5 px-0.5 text-center ${
              activeTab === id
                ? "text-blue-600 border-b-2 border-blue-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === "trip" && (
          <div className="space-y-4">
            {routes.length > 0 && <DisruptionBanner routes={routes} />}

            {routes.length > 0 && selectedRoute !== null && routes[selectedRoute] && (
              <LeaveNowButton route={routes[selectedRoute]} />
            )}

            {routes.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-semibold text-gray-900 text-sm">
                    {routes.length} Route Option{routes.length !== 1 ? "s" : ""}
                  </h2>
                  <button
                    onClick={handleCompare}
                    disabled={compareLoading}
                    className="text-xs bg-purple-600 text-white px-3 py-1.5 rounded hover:bg-purple-700 disabled:opacity-50"
                  >
                    {compareLoading ? "..." : "Compare Modes"}
                  </button>
                </div>
                <div className="space-y-2">
                  {routes.map((route, idx) => (
                    <RouteCard
                      key={idx}
                      option={route}
                      selected={selectedRoute === idx}
                      onClick={() => setSelectedRoute(idx)}
                    />
                  ))}
                </div>
              </div>
            )}

            {compareData && (
              <div>
                <h2 className="font-semibold text-gray-900 text-sm mb-2">
                  All Modes
                  {compareData.recommended && (
                    <span className="ml-2 text-xs text-purple-600">
                      Best: {compareData.recommended}
                    </span>
                  )}
                </h2>
                <ModeCompare
                  modes={compareData.modes}
                  recommended={compareData.recommended}
                  delayRisk={compareData.delay_risk}
                />
              </div>
            )}

            {planParams && <IntercityModes planParams={planParams} />}
            {planParams && <WhatIfPanel planParams={planParams} />}

            {!planParams && (
              <div className="text-xs text-gray-500 text-center py-8">
                Set origin and destination on the map, then plan a trip to
                see options here.
              </div>
            )}
          </div>
        )}

        {activeTab === "insights" && (
          <InsightsPanel planParams={planParams} />
        )}

        {activeTab === "budget" && (
          <BudgetPanel planParams={planParams} />
        )}

        {activeTab === "ask" && (
          <ChatPanel planParams={planParams} />
        )}
      </div>

      {/* Attribution required by Metrolinx Access and Use Agreement */}
      <div className="text-[9px] text-gray-400 px-3 py-2 border-t leading-tight break-words">
        Data used in this product or service is provided with the permission
        of Metrolinx. Metrolinx makes no representations or warranties of any
        kind, express or implied, and assumes no responsibility for the
        accuracy or currency of the data. DRT data via the Region of Durham
        open data portal.
      </div>
    </>
  );

  const tripForm = (
    <>
      {frequentTrips.length > 0 && !origin && (
        <div className="mb-2">
          <div className="text-[10px] text-gray-400 mb-1">Recent trips:</div>
          <div className="flex flex-wrap gap-1">
            {frequentTrips.map((t, i) => (
              <button
                key={i}
                onClick={() => {
                  setOrigin({ lat: t.origin.lat, lon: t.origin.lon });
                  setDestination({ lat: t.destination.lat, lon: t.destination.lon });
                }}
                className="text-[10px] bg-gray-100 hover:bg-gray-200 rounded-full px-2 py-1 text-gray-600"
              >
                📍 {t.origin.lat.toFixed(3)},{t.origin.lon.toFixed(3)} →{" "}
                {t.destination.lat.toFixed(3)},{t.destination.lon.toFixed(3)}
                {t.count > 1 && ` (×${t.count})`}
              </button>
            ))}
          </div>
        </div>
      )}
      <RouteForm
        origin={origin}
        destination={destination}
        onPlan={handlePlan}
        loading={loading}
        onOriginChange={setOrigin}
        onDestinationChange={setDestination}
      />
      {origin && destination && (
        <div className="text-[10px] text-gray-400 mt-1">
          {origin.lat.toFixed(4)},{origin.lon.toFixed(4)} →{" "}
          {destination.lat.toFixed(4)},{destination.lon.toFixed(4)}
        </div>
      )}
    </>
  );

  const actionButtons = (
    <div className="flex gap-2 flex-wrap">
      <button
        onClick={() => setClickMode(clickMode === "origin" ? null : "origin")}
        className={`px-3 py-1.5 rounded text-sm font-medium ${
          clickMode === "origin"
            ? "bg-green-600 text-white"
            : "bg-green-100 text-green-700 hover:bg-green-200"
        }`}
      >
        {clickMode === "origin" ? "Tap map: Origin" : "Set Origin"}
      </button>
      <button
        onClick={() => setClickMode(clickMode === "destination" ? null : "destination")}
        className={`px-3 py-1.5 rounded text-sm font-medium ${
          clickMode === "destination"
            ? "bg-red-600 text-white"
            : "bg-red-100 text-red-700 hover:bg-red-200"
        }`}
      >
        {clickMode === "destination" ? "Tap map: Dest" : "Set Destination"}
      </button>
      <button
        onClick={() => setShowVehicles(!showVehicles)}
        className={`px-3 py-1.5 rounded text-sm font-medium ${
          showVehicles
            ? "bg-amber-600 text-white"
            : "bg-amber-100 text-amber-700 hover:bg-amber-200"
        }`}
      >
        {showVehicles ? "Hide Buses" : "Show Buses"}
      </button>
    </div>
  );

  // Bottom-sheet drag handlers (mobile)
  const onSheetTouchStart = (e) => {
    touchStartY.current = e.touches[0].clientY;
  };
  const onSheetTouchEnd = (e) => {
    if (touchStartY.current === null) return;
    const dy = e.changedTouches[0].clientY - touchStartY.current;
    touchStartY.current = null;
    if (dy < -40) setSheet((s) => (s === "peek" ? "half" : "full"));
    else if (dy > 40) setSheet((s) => (s === "full" ? "half" : "peek"));
  };

  const sheetHeights = {
    peek: "max-h-[38vh]",
    half: "max-h-[62vh]",
    full: "max-h-[92vh]",
  };

  return (
    <main className="h-screen flex flex-col overflow-hidden">
      {/* Header — compact on mobile */}
      <header className="bg-white border-b px-3 py-2 md:px-4 md:py-3 flex items-center justify-between gap-2 flex-wrap z-20">
        <h1 className="text-base md:text-xl font-bold text-gray-900">
          Durham Commute Planner
        </h1>
        <div className="hidden md:block">{actionButtons}</div>
        {/* Mobile: icon-size buttons */}
        <div className="flex md:hidden gap-1.5">{actionButtons}</div>
      </header>

      {/* ============ Content area: one map, responsive panel ============ */}
      <div className="flex-1 relative overflow-hidden">
        {/* The single map element — always rendered, fills the area */}
        <div ref={mapContainer} className="absolute inset-0 w-full h-full" />
        {!mapLoaded && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-100 pointer-events-none">
            <div className="text-gray-500">Loading map...</div>
          </div>
        )}

        {/* Desktop: left panel overlays the map */}
        <aside className="hidden md:flex absolute left-0 top-0 bottom-0 w-96 bg-gray-50 border-r flex-col overflow-hidden shadow-lg z-10">
          <div className="p-4 pb-2 border-b bg-white">{tripForm}</div>
          {plannerContent}
        </aside>

        {/* Mobile: bottom sheet overlays the map */}
        <div
          className={`md:hidden absolute bottom-0 inset-x-0 bg-gray-50 rounded-t-2xl shadow-2xl border-t flex flex-col transition-all duration-200 z-10 ${sheetHeights[sheet]}`}
          style={{ height: sheet === "full" ? "92%" : sheet === "half" ? "62%" : "38%" }}
        >
          {/* Drag handle */}
          <div
            className="pt-2 pb-1 cursor-grab touch-none flex flex-col items-center bg-white rounded-t-2xl"
            onTouchStart={onSheetTouchStart}
            onTouchEnd={onSheetTouchEnd}
            onClick={() => setSheet((s) => (s === "full" ? "half" : "full"))}
          >
            <div className="w-10 h-1.5 bg-gray-300 rounded-full" />
          </div>

          {/* Trip form */}
          <div className="px-3 pb-2 border-b bg-white">{tripForm}</div>

          {plannerContent}
        </div>
      </div>

      <InstallPrompt />
    </main>
  );
}