import { describe, expect, it } from "vitest";
import { getSpatialAccess } from "./spatialAccess";

const polygon = {
  type: "MultiPolygon",
  coordinates: [
    [
      [
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 0],
      ],
    ],
  ],
};
const rule = {
  id: 1,
  allowedGroups: [{ id: "team" }],
  operations: [{ id: "map" }],
  securedLayers: [{ id: "layer" }, { id: "child" }],
  allowedArea: polygon,
};

describe("group spatial access", () => {
  it("combines server-filtered user rules across different groups", () => {
    const access = getSpatialAccess(
      [rule, { ...rule, id: 2, allowedGroups: [{ id: "other" }] }],
      undefined,
      "map",
      "layer",
      true,
    );
    expect(access.status).toBe("restricted");
    expect(access.areas.features).toHaveLength(2);
  });
  it("denies an empty filtered result when the service has rules", () => {
    expect(getSpatialAccess([], "team", "map", "layer", true).status).toBe(
      "denied",
    );
  });
  it("combines all applicable areas including rules for every group", () => {
    const result = getSpatialAccess(
      [rule, { ...rule, id: 2, allowedGroups: [] }],
      "team",
      "map",
      "layer",
    );
    expect(result.status).toBe("restricted");
    expect(result.areas.features).toHaveLength(2);
  });
  it.each([
    ["other", "map", "layer"],
    ["team", "info", "layer"],
    ["team", "map", "other"],
  ])(
    "denies unmatched group/operation/layer %s %s %s",
    (group, operation, layer) => {
      expect(getSpatialAccess([rule], group, operation, layer).status).toBe(
        "denied",
      );
    },
  );
  it("includes stored descendant memberships", () => {
    expect(getSpatialAccess([rule], "team", "map", "child").status).toBe(
      "restricted",
    );
  });
  it("lets an applicable unrestricted rule override polygon restrictions", () => {
    const result = getSpatialAccess(
      [rule, { ...rule, id: 2, allowedArea: null }],
      "team",
      "map",
      "layer",
    );
    expect(result.status).toBe("unrestricted");
    expect(result.areas.features).toEqual([]);
  });
  it("does not apply an unrelated unrestricted rule", () => {
    expect(
      getSpatialAccess(
        [
          rule,
          {
            ...rule,
            id: 2,
            allowedGroups: [{ id: "other" }],
            allowedArea: null,
          },
        ],
        "team",
        "map",
        "layer",
      ).status,
    ).toBe("restricted");
  });
  it("allows spatial access when the service has no security rules", () => {
    expect(getSpatialAccess([], "team", "map", "layer").status).toBe(
      "unrestricted",
    );
  });
  it("compares numeric relationship ids with selected string ids", () => {
    expect(
      getSpatialAccess(
        [{ ...rule, allowedGroups: [{ id: 1 }] }],
        "1",
        "map",
        "layer",
      ).status,
    ).toBe("restricted");
  });
});
