import type { GeoJsonObject } from "geojson";
import L from "leaflet";

// Geometry fields can arrive as GeoJSON objects or serialized GeoJSON.
export const getCoverageBounds = (
  value: unknown,
): L.LatLngBounds | undefined => {
  if (!value) return undefined;
  try {
    const geometry = typeof value === "string" ? JSON.parse(value) : value;
    const bounds = L.geoJSON(geometry as GeoJsonObject).getBounds();
    if (!bounds.isValid()) return undefined;
    const coordinates = [
      bounds.getSouth(),
      bounds.getNorth(),
      bounds.getWest(),
      bounds.getEast(),
    ];
    if (
      !coordinates.every(Number.isFinite) ||
      bounds.getSouth() < -90 ||
      bounds.getNorth() > 90 ||
      bounds.getWest() < -180 ||
      bounds.getEast() > 180
    )
      return undefined;
    return bounds;
  } catch {
    return undefined;
  }
};
