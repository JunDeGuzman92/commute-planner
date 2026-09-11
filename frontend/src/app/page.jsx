"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import RouteForm from "../components/RouteForm";
import RouteCard from "../components/RouteCard";

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

  useEffect(() => {
    if (map.current || !mapContainer.current) return;

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
        map.current.fitBounds(bounds, { padding: 50 });
      }

      setRouteLines(newLineIds);
    },
    [mapLoaded, clearRouteLines]
  );

  const handlePlan = async (planData) => {
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8101/plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(planData),
      });
      const data = await res.json();
      setRoutes(data);
      if (data.length > 0) {
        setSelectedRoute(0);
        drawRoute(data[0]);
      }
    } catch (e) {
      console.error("Plan failed:", e);
      alert("Failed to plan route. Is the backend running on port 8101?");
    } finally {
      setLoading(false);
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
        const res = await fetch("http://localhost:8101/vehicles");
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

  return (
    <main className="h-screen flex flex-col">
      <header className="bg-white border-b px-4 py-3 flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Durham Commute Planner</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setClickMode(clickMode === "origin" ? null : "origin")}
            className={`px-3 py-1 rounded text-sm font-medium ${
              clickMode === "origin"
                ? "bg-green-600 text-white"
                : "bg-green-100 text-green-700 hover:bg-green-200"
            }`}
          >
            {clickMode === "origin" ? "Click map for Origin" : "Set Origin"}
          </button>
          <button
            onClick={() => setClickMode(clickMode === "destination" ? null : "destination")}
            className={`px-3 py-1 rounded text-sm font-medium ${
              clickMode === "destination"
                ? "bg-red-600 text-white"
                : "bg-red-100 text-red-700 hover:bg-red-200"
            }`}
          >
            {clickMode === "destination" ? "Click map for Destination" : "Set Destination"}
          </button>
          <button
            onClick={() => setShowVehicles(!showVehicles)}
            className={`px-3 py-1 rounded text-sm font-medium ${
              showVehicles
                ? "bg-amber-600 text-white"
                : "bg-amber-100 text-amber-700 hover:bg-amber-200"
            }`}
          >
            {showVehicles ? "Hide Buses" : "Show Buses"}
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-96 bg-gray-50 border-r overflow-y-auto p-4 flex flex-col gap-4">
          <RouteForm
            origin={origin}
            destination={destination}
            onPlan={handlePlan}
            loading={loading}
            onOriginChange={setOrigin}
            onDestinationChange={setDestination}
          />

          {origin && (
            <div className="text-sm text-gray-600 bg-green-50 p-2 rounded">
              <strong>Origin:</strong> {origin.lat.toFixed(5)}, {origin.lon.toFixed(5)}
            </div>
          )}
          {destination && (
            <div className="text-sm text-gray-600 bg-red-50 p-2 rounded">
              <strong>Destination:</strong> {destination.lat.toFixed(5)}, {destination.lon.toFixed(5)}
            </div>
          )}

          {routes.length > 0 && (
            <div className="mt-4">
              <h2 className="font-semibold text-gray-900 mb-2">
                {routes.length} Route Option{routes.length !== 1 ? "s" : ""}
              </h2>
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
        </aside>

        <div className="flex-1 relative">
          <div ref={mapContainer} className="absolute inset-0" />
          {!mapLoaded && (
            <div className="absolute inset-0 flex items-center justify-center bg-gray-100">
              <div className="text-gray-500">Loading map...</div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}