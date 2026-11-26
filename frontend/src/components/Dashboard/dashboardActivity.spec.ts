import { describe, expect, it } from "vitest";

import { dashboardActivity, type ActivitySource } from "./dashboardActivity";
import { dashboardStatistics } from "./dashboardStatistics";

const source = (resource: string, added: number, updated = 0, deleted = 0): ActivitySource => ({
  resource,
  statistics: dashboardStatistics([
    { id: "2026-04-01", day: "2026-04-01", new: added, updated, deleted },
  ], 1, 100, 7, "2026-04-01"),
});

describe("dashboard activity", () => {
  it("sums nonnegative events by day, never inventory or distinct objects", () => {
    const result = dashboardActivity([source("CatalogueService", 2, 3, 4), source("DatasetMetadataRecord", 5, 6, 7)]);
    expect(result).toMatchObject({ status: "ready", totals: { new: 7, updated: 9, deleted: 11 } });
    if (result.status !== "ready") throw Error("missing events");
    expect(result.days).toHaveLength(7);
    expect(result.days[0]).toEqual({ id: "2026-03-26", new: 0, updated: 0, deleted: 0 });
    expect(result.days.at(-1)).toEqual({ id: "2026-04-01", new: 7, updated: 9, deleted: 11 });
    expect(result.days.at(-1)).not.toHaveProperty("total");
  });

  it.each(["loading", "error", "partial", "unsupported"] as const)("does not silently sum a %s resource", status => {
    expect(dashboardActivity([source("CatalogueService", 5), {
      resource: "DatasetMetadataRecord", statistics: { status },
    }])).toEqual({ status });
  });

  it("distinguishes zero events from missing coverage", () => {
    expect(dashboardActivity([source("CatalogueService", 0)])).toMatchObject({
      status: "ready", totals: { new: 0, updated: 0, deleted: 0 },
    });
    expect(dashboardActivity([])).toEqual({ status: "unsupported" });
  });

  it("refuses mismatched daily windows", () => {
    const shorter = source("DatasetMetadataRecord", 2);
    if (shorter.statistics.status === "ready") shorter.statistics.days.pop();
    expect(dashboardActivity([source("CatalogueService", 1), shorter])).toEqual({ status: "partial" });
    const shifted = source("DatasetMetadataRecord", 2);
    if (shifted.statistics.status === "ready") shifted.statistics.days[0].id = "2026-03-25";
    expect(dashboardActivity([source("CatalogueService", 1), shifted])).toEqual({ status: "partial" });
  });
});
