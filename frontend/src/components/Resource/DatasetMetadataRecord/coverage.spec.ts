import { describe, expect, it } from "vitest";
import { getCoverageBounds } from "./coverage";
const geometry = {
  type: "MultiPolygon",
  coordinates: [
    [
      [
        [6, 49],
        [7, 49],
        [7, 50],
        [6, 50],
        [6, 49],
      ],
    ],
  ],
};
describe("dataset coverage", () => {
  it("reads objects and serialized GeoJSON", () => {
    for (const input of [geometry, JSON.stringify(geometry)]) {
      expect(getCoverageBounds(input)?.getWest()).toBe(6);
      expect(getCoverageBounds(input)?.getNorth()).toBe(50);
    }
  });
  it("ignores missing, malformed, empty and out-of-range geometry", () => {
    for (const input of [
      null,
      undefined,
      "",
      "{",
      {},
      { type: "MultiPolygon", coordinates: [] },
      { type: "Point", coordinates: [900, 100] },
    ])
      expect(getCoverageBounds(input)).toBeUndefined();
  });
});
