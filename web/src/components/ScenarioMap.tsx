import { useEffect, useMemo } from "react";
import { MapContainer, TileLayer, GeoJSON, CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-draw";
import "leaflet-draw/dist/leaflet.draw.css";
import type { FeatureCollection } from "geojson";
import type { BBox, LatLon, Rsu } from "../api/client";

/* Captura de rectángulo con leaflet-draw → devuelve el bbox al padre. */
function DrawRectangle({ onBbox }: { onBbox: (b: BBox) => void }) {
  const map = useMap();
  useEffect(() => {
    const group = new L.FeatureGroup();
    map.addLayer(group);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const control = new (L.Control as any).Draw({
      draw: {
        polyline: false, polygon: false, circle: false, marker: false, circlemarker: false,
        rectangle: { shapeOptions: { color: "#2557a7", weight: 2, fillColor: "#2557a7", fillOpacity: 0.08 } },
      },
      edit: { featureGroup: group, edit: false, remove: false },
    });
    map.addControl(control);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const onCreated = (e: any) => {
      group.clearLayers();
      group.addLayer(e.layer);
      const b = e.layer.getBounds();
      onBbox({ min_lon: b.getWest(), min_lat: b.getSouth(), max_lon: b.getEast(), max_lat: b.getNorth() });
    };
    map.on(L.Draw.Event.CREATED, onCreated);
    return () => {
      map.off(L.Draw.Event.CREATED, onCreated);
      map.removeControl(control);
      map.removeLayer(group);
    };
  }, [map, onBbox]);
  return null;
}

function FitBounds({ bounds }: { bounds?: [LatLon, LatLon] | null }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [24, 24] });
    // el contenedor puede cambiar de tamaño tras el layout: re-invalidar
    const id = setTimeout(() => map.invalidateSize(), 200);
    return () => clearTimeout(id);
  }, [bounds, map]);
  return null;
}

export interface MapProps {
  edificios?: LatLon[][] | null;
  candidatas?: Rsu[] | null;
  desplegadas?: Rsu[] | null;
  bounds?: [LatLon, LatLon] | null;
  onBbox?: (b: BBox) => void;
}

export default function ScenarioMap({ edificios, candidatas, desplegadas, bounds, onBbox }: MapProps) {
  const desplegadasIds = useMemo(() => new Set((desplegadas ?? []).map((r) => r.id)), [desplegadas]);

  const geojson = useMemo<FeatureCollection | null>(() => {
    if (!edificios || edificios.length === 0) return null;
    return {
      type: "FeatureCollection",
      features: edificios.map((ring) => ({
        type: "Feature",
        properties: {},
        geometry: { type: "Polygon", coordinates: [ring.map(([lat, lon]) => [lon, lat])] },
      })),
    };
  }, [edificios]);

  return (
    <div className="plot">
      <span className="corner tl" /><span className="corner tr" />
      <span className="corner bl" /><span className="corner br" />
      <MapContainer center={[-0.2186, -78.5097]} zoom={13} zoomControl
        style={{ height: "100%", width: "100%" }} preferCanvas>
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; OpenStreetMap &copy; CARTO' />
        {onBbox && <DrawRectangle onBbox={onBbox} />}
        <FitBounds bounds={bounds} />

        {geojson && (
          <GeoJSON key={geojson.features.length} data={geojson}
            style={{ color: "#d97b2f", weight: 0.6, fillColor: "#f4a25a", fillOpacity: 0.4 }} />
        )}

        {/* RSU candidatas no desplegadas (gris) */}
        {(candidatas ?? [])
          .filter((r) => !desplegadasIds.has(r.id))
          .map((r) => (
            <CircleMarker key={`c-${r.id}`} center={[r.lat, r.lon]} radius={4}
              pathOptions={{ color: "#94a3b8", weight: 1, fillColor: "#cbd5e1", fillOpacity: 0.6 }} />
          ))}

        {/* RSU desplegadas (verde, resaltadas) */}
        {(desplegadas ?? []).map((r) => (
          <CircleMarker key={`d-${r.id}`} center={[r.lat, r.lon]} radius={7}
            pathOptions={{ color: "#166534", weight: 2, fillColor: "#22c55e", fillOpacity: 0.95 }} />
        ))}
      </MapContainer>
    </div>
  );
}
