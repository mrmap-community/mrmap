import type { GeoJsonObject } from 'geojson';

// Geometry values reach the map either as GeoJSON objects or as serialized
// GeoJSON: the OpenAPI schema declares geometry fields and filter parameters
// as `type: string, format: "geojson"` (see `extras/schema.py`), so the
// JSON:API layer answers them as JSON strings, and search-area filters keep
// them serialized. The explorer's `getCoverageBounds` normalizes the same
// shape before computing bounds; this is its counterpart before drawing.
//
// Returns a value `L.geoJSON` can render, or `undefined` for absent values
// and for values without a usable GeoJSON `type`. Never throws; serialized
// nested geometry slots are parsed because leaflet only tolerates strings at
// the top level and throws on a `Feature` whose `geometry` is one.

const GEOMETRY_TYPES = [
  'Point',
  'MultiPoint',
  'LineString',
  'MultiLineString',
  'Polygon',
  'MultiPolygon',
  'GeometryCollection',
] as const;

const DOCUMENT_TYPES = ['Feature', 'FeatureCollection'] as const;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const parseJson = (value: string): unknown => {
  try {
    return JSON.parse(value);
  } catch {
    return undefined;
  }
};

const hasType = (
  value: unknown,
  types: readonly string[],
): value is Record<string, unknown> =>
  isRecord(value) && typeof value.type === 'string' && types.includes(value.type);

// An unrenderable nested geometry becomes `null`, which leaflet draws as
// nothing; that keeps the remaining features of a collection renderable
// instead of letting one broken member throw away the whole layer.
const normalizeGeometrySlot = (geometry: unknown): unknown => {
  if (geometry === null || geometry === undefined) return null;
  const value = typeof geometry === 'string' ? parseJson(geometry) : geometry;
  return hasType(value, GEOMETRY_TYPES) ? value : null;
};

export const normalizeGeoJson = (value: unknown): GeoJsonObject | undefined => {
  if (value === undefined || value === null || value === '') return undefined;
  const candidate = typeof value === 'string' ? parseJson(value) : value;
  if (!hasType(candidate, [...GEOMETRY_TYPES, ...DOCUMENT_TYPES])) return undefined;
  switch (candidate.type) {
    case 'Feature':
      return {
        ...candidate,
        geometry: normalizeGeometrySlot(candidate.geometry),
      } as unknown as GeoJsonObject;
    case 'FeatureCollection': {
      const features = Array.isArray(candidate.features) ? candidate.features : [];
      return {
        ...candidate,
        features: features.map((feature) =>
          isRecord(feature)
            ? { ...feature, geometry: normalizeGeometrySlot(feature.geometry) }
            : feature,
        ),
      } as unknown as GeoJsonObject;
    }
    case 'GeometryCollection': {
      const geometries = Array.isArray(candidate.geometries)
        ? candidate.geometries
        : [];
      return {
        ...candidate,
        geometries: geometries.map(normalizeGeometrySlot),
      } as unknown as GeoJsonObject;
    }
    default:
      return candidate as unknown as GeoJsonObject;
  }
};

export default normalizeGeoJson;
