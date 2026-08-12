import { useEffect, useMemo, useState } from "react";
import {
  MapContainer, TileLayer, GeoJSON, CircleMarker, Circle, Polyline, Rectangle,
  useMap, useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { FeatureCollection } from "geojson";
import type { BBox, LatLon, Rsu, ConnFrame } from "../api/client";

/**
 * Selección del área por DOS clics (sin leaflet-draw, que rompe con Leaflet
 * moderno). Primer clic fija una esquina; el movimiento del ratón dibuja la
 * previsualización; el segundo clic cierra el rectángulo y entrega el bbox.
 * Si no se está dibujando, muestra el rectángulo ya confirmado (`bbox`).
 */
function DrawRectangle({ active, bbox, onBbox }: {
  active: boolean; bbox?: BBox | null; onBbox: (b: BBox) => void;
}) {
  const [c1, setC1] = useState<L.LatLng | null>(null);
  const [cur, setCur] = useState<L.LatLng | null>(null);

  useMapEvents({
    click(e) {
      if (!active) return;
      if (!c1) { setC1(e.latlng); setCur(e.latlng); return; }
      const b = L.latLngBounds(c1, e.latlng);
      onBbox({ min_lon: b.getWest(), min_lat: b.getSouth(), max_lon: b.getEast(), max_lat: b.getNorth() });
      setC1(null); setCur(null);
    },
    mousemove(e) { if (active && c1) setCur(e.latlng); },
  });

  // Reiniciar la esquina temporal cuando se apaga el modo dibujo.
  useEffect(() => { if (!active) { setC1(null); setCur(null); } }, [active]);

  if (active && c1 && cur) {
    return <Rectangle bounds={L.latLngBounds(c1, cur)}
      pathOptions={{ color: "#2557a7", weight: 2, dashArray: "5 5", fillColor: "#2557a7", fillOpacity: 0.08 }} />;
  }
  if (bbox) {
    return <Rectangle bounds={[[bbox.min_lat, bbox.min_lon], [bbox.max_lat, bbox.max_lon]]}
      pathOptions={{ color: "#2557a7", weight: 2, fillColor: "#2557a7", fillOpacity: 0.06 }} />;
  }
  return null;
}

/** Encaja la vista al escenario y re-invalida el tamaño tras el layout. */
function FitBounds({ bounds }: { bounds?: [LatLon, LatLon] | null }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [24, 24] });
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
  frame?: ConnFrame | null;
  drawing?: boolean;
  bbox?: BBox | null;
  cobertura?: number;   // radio de cobertura en metros (0 = no dibujar)
  onBbox?: (b: BBox) => void;
}

export default function ScenarioMap({
  edificios, candidatas, desplegadas, bounds, frame, drawing, bbox, cobertura, onBbox,
}: MapProps) {
  const desplegadasIds = useMemo(() => new Set((desplegadas ?? []).map((r) => r.id)), [desplegadas]);
  // Cobertura: si hay despliegue óptimo, se dibuja sobre las desplegadas;
  // si todavía no, sobre las candidatas.
  const cubiertas = (desplegadas && desplegadas.length ? desplegadas : candidatas) ?? [];

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
    <div className={`plot ${drawing ? "drawing" : ""}`}>
      <span className="corner tl" /><span className="corner tr" />
      <span className="corner bl" /><span className="corner br" />
      <MapContainer center={[-0.2186, -78.5097]} zoom={13} zoomControl
        style={{ height: "100%", width: "100%" }} preferCanvas>
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; OpenStreetMap &copy; CARTO' />
        {onBbox && <DrawRectangle active={!!drawing} bbox={bbox} onBbox={onBbox} />}
        <FitBounds bounds={bounds} />

        {geojson && (
          <GeoJSON key={geojson.features.length} data={geojson}
            style={{ color: "#d97b2f", weight: 0.6, fillColor: "#f4a25a", fillOpacity: 0.4 }} />
        )}

        {/* Radio de cobertura de las RSU */}
        {cobertura && cobertura > 0 && cubiertas.map((r) => (
          <Circle key={`cov-${r.id}`} center={[r.lat, r.lon]} radius={cobertura}
            pathOptions={{ color: "#0f9d6b", weight: 1, opacity: 0.5, fillColor: "#0f9d6b",
              fillOpacity: 0.06, dashArray: "4 4" }} />
        ))}

        {(candidatas ?? [])
          .filter((r) => !desplegadasIds.has(r.id))
          .map((r) => (
            <CircleMarker key={`c-${r.id}`} center={[r.lat, r.lon]} radius={5}
              pathOptions={{ color: "#7f1d1d", weight: 1, fillColor: "#ef4444", fillOpacity: 0.85 }} />
          ))}

        {(desplegadas ?? []).map((r) => (
          <CircleMarker key={`d-${r.id}`} center={[r.lat, r.lon]} radius={7}
            pathOptions={{ color: "#166534", weight: 2, fillColor: "#22c55e", fillOpacity: 0.95 }} />
        ))}

        {/* Conectividad del instante: enlaces V2V (ámbar) + V2I (verde) + vehículos */}
        {frame?.v2v.map((l, i) => (
          <Polyline key={`vv-${i}`} positions={[l.a, l.b]}
            pathOptions={{ color: "#b9770b", weight: 2, opacity: 0.7, dashArray: "5 4" }} />
        ))}
        {frame?.v2i.map((l, i) => (
          <Polyline key={`vi-${i}`} positions={[l.a, l.b]}
            pathOptions={{ color: "#0f9d6b", weight: 1.5, opacity: 0.5, dashArray: "4 4" }} />
        ))}
        {frame?.vehiculos.map((v) => (
          <CircleMarker key={`veh-${v.id}`} center={[v.lat, v.lon]} radius={5}
            pathOptions={{ color: "#16407f", weight: 2, fillColor: "#2557a7", fillOpacity: 0.95 }} />
        ))}
      </MapContainer>
    </div>
  );
}
