import { latLngBounds } from "leaflet";
import { describe, expect, it } from "vitest";

import { boundsToExtent, extentBounds, validExtent } from "./utils";

describe("viewer extent", () => {
  it("accepts zero-degree coordinates, and rejects invalid, reversed or degenerate extents", () => {
    expect(validExtent([0, -2, 4, 0])).toBe(true);
    expect(validExtent([-180, -90, 180, 90])).toBe(true);
    for (const value of [
      null,
      undefined,
      [],
      [0, 0, 0, 0],
      [4, 0, 0, 8],
      [0, 0, 4, Infinity],
      [-200, 0, 4, 8],
      // the extent of a navigation is untyped data and may arrive as anything
      "0,0,4,8",
      {},
    ])
      expect(validExtent(value as number[] | null)).toBe(false);
  });
  it("turns an area of interest into the bounds leaflet wants and back", () => {
    const bounds = extentBounds([10, 20, 30, 40]);
    expect(bounds.getWest()).toBe(10);
    expect(bounds.getSouth()).toBe(20);
    expect(boundsToExtent(bounds)).toEqual([10, 20, 30, 40]);
  });
  it("clamps a viewport that reaches over a pole or wraps the world to one world", () => {
    expect(boundsToExtent(latLngBounds([[-95, -180], [95, 180]]))).toEqual([
      -180, -90, 180, 90,
    ]);
    expect(boundsToExtent(latLngBounds([[-10, -200], [10, 200]]))).toEqual([
      -180, -10, 180, 10,
    ]);
  });
});
