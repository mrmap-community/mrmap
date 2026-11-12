import L from "leaflet";
import { describe, expect, it } from "vitest";

import { normalizeGeoJson } from "./normalizeGeoJson";

const POLYGON = {
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [0, 1],
      [1, 1],
      [1, 0],
      [0, 0],
    ],
  ],
};

const FEATURE = { type: "Feature", properties: {}, geometry: POLYGON };

describe("normalizeGeoJson", () => {
  it("passes valid geometry objects through untouched", () => {
    expect(normalizeGeoJson(POLYGON)).toBe(POLYGON);
    expect(normalizeGeoJson(FEATURE)).toEqual(FEATURE);
  });

  it("parses serialized GeoJSON strings, objects and collections alike", () => {
    expect(normalizeGeoJson(JSON.stringify(POLYGON))).toEqual(POLYGON);
    expect(normalizeGeoJson(JSON.stringify(FEATURE))).toEqual(FEATURE);
    expect(
      normalizeGeoJson(
        JSON.stringify({ type: "FeatureCollection", features: [FEATURE] }),
      ),
    ).toEqual({ type: "FeatureCollection", features: [FEATURE] });
  });

  it("parses the serialized nested geometries the JSON:API answers with", () => {
    // AccessRulesSummary builds this shape from `rule.allowedArea`, which the
    // API answers as a serialized geometry string
    const collection = {
      type: "FeatureCollection",
      features: [{ type: "Feature", properties: {}, geometry: JSON.stringify(POLYGON) }],
    };
    expect(normalizeGeoJson(collection)).toEqual({
      type: "FeatureCollection",
      features: [FEATURE],
    });
    expect(
      normalizeGeoJson({ type: "Feature", properties: {}, geometry: JSON.stringify(POLYGON) }),
    ).toEqual(FEATURE);
    expect(
      normalizeGeoJson({ type: "GeometryCollection", geometries: [JSON.stringify(POLYGON)] }),
    ).toEqual({ type: "GeometryCollection", geometries: [POLYGON] });
  });

  it("keeps legitimate empty geometries empty instead of dropping them", () => {
    expect(
      normalizeGeoJson({ type: "Feature", properties: {}, geometry: null }),
    ).toEqual({ type: "Feature", properties: {}, geometry: null });
    expect(
      normalizeGeoJson({ type: "Feature", properties: {} }),
    ).toEqual({ type: "Feature", properties: {}, geometry: null });
    expect(normalizeGeoJson({ type: "FeatureCollection", features: [] })).toEqual({
      type: "FeatureCollection",
      features: [],
    });
  });

  it("neutralizes single unusable nested geometries so the rest renders", () => {
    expect(
      normalizeGeoJson({
        type: "FeatureCollection",
        features: [FEATURE, { type: "Feature", properties: {}, geometry: "not json" }],
      }),
    ).toEqual({
      type: "FeatureCollection",
      features: [FEATURE, { type: "Feature", properties: {}, geometry: null }],
    });
  });

  it("treats absent values as no geometry", () => {
    expect(normalizeGeoJson(undefined)).toBeUndefined();
    expect(normalizeGeoJson(null)).toBeUndefined();
    expect(normalizeGeoJson("")).toBeUndefined();
  });

  it("rejects objects without a usable GeoJSON type", () => {
    expect(normalizeGeoJson({})).toBeUndefined();
    // the shape a leaflet LatLngBounds has, observed reaching the map live
    expect(
      normalizeGeoJson({
        _southEast: { lat: 1, lng: 1 },
        _northWest: { lat: 0, lng: 0 },
      }),
    ).toBeUndefined();
    expect(normalizeGeoJson({ type: "Nonsense" })).toBeUndefined();
    expect(normalizeGeoJson({ type: 42 })).toBeUndefined();
  });

  it("rejects malformed strings and non-object JSON", () => {
    expect(normalizeGeoJson("not json")).toBeUndefined();
    expect(normalizeGeoJson("123")).toBeUndefined();
    expect(normalizeGeoJson('"Polygon"')).toBeUndefined();
  });

  it("rejects values that are no GeoJSON at all", () => {
    expect(normalizeGeoJson([])).toBeUndefined();
    expect(normalizeGeoJson([POLYGON])).toBeUndefined();
    expect(normalizeGeoJson(42)).toBeUndefined();
    expect(normalizeGeoJson(true)).toBeUndefined();
  });

  it("pins the leaflet behaviour this normalizer exists for", () => {
    // every value below makes the project's own leaflet (1.9) throw with
    // "Invalid GeoJSON object." - the audit's console line and the silently
    // empty map
    const thrownByLeaflet: unknown[] = [
      JSON.stringify(POLYGON),
      "{}",
      "not json",
      {},
      { type: "Nonsense" },
      { _southEast: { lat: 1, lng: 1 }, _northWest: { lat: 0, lng: 0 } },
      42,
    ];
    thrownByLeaflet.forEach((value) => {
      expect(() => L.geoJSON(value as never)).toThrow(/Invalid GeoJSON/);
      // what the normalizer makes of such a value is either nothing at all -
      // the component then shows the hint - or a value leaflet renders
      const normalized = normalizeGeoJson(value);
      if (normalized !== undefined) {
        expect(() => L.geoJSON(normalized)).not.toThrow();
      }
    });

    // and everything it accepts from a usable value is drawable
    [
      POLYGON,
      FEATURE,
      JSON.stringify(POLYGON),
      { type: "Feature", properties: {}, geometry: JSON.stringify(POLYGON) },
    ].forEach((value) => {
      expect(() => L.geoJSON(normalizeGeoJson(value) as never)).not.toThrow();
    });
  });
});
