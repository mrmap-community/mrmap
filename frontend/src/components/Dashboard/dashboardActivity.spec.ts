import { describe, expect, it } from "vitest";

import { dashboardActivity, type ActivitySource } from "./dashboardActivity";
import { dashboardStatistics } from "./dashboardStatistics";

const source = (resource: string, added: number, updated = 0, deleted = 0): ActivitySource => ({
  resource,
  statistics: dashboardStatistics([
    { id: "2026-04-01", day: "2026-04-01", new: added, updated, deleted },
  ], 1, 100, 7, "2026-04-01"),
});

const seriesOf = (result: ReturnType<typeof dashboardActivity>) => {
  if (result.status !== "ready") throw Error(`no lines: ${result.status}`);
  return result.series;
};

describe("dashboard activity", () => {
  it("draws one line per verified resource, counted as the events of its own day", () => {
    const result = dashboardActivity([source("CatalogueService", 2, 3, 4), source("DatasetMetadataRecord", 5, 6, 7)]);
    if (result.status !== "ready") throw Error("missing events");
    expect(result.days).toHaveLength(7);
    expect(result.days[0]).toBe("2026-03-26");
    expect(result.days.at(-1)).toBe("2026-04-01");
    expect(result.series).toEqual([
      { resource: "CatalogueService", data: [0, 0, 0, 0, 0, 0, 9], total: 9 },
      { resource: "DatasetMetadataRecord", data: [0, 0, 0, 0, 0, 0, 18], total: 18 },
    ]);
  });

  it("never sums the events of two resources into one line", () => {
    const lines = seriesOf(dashboardActivity([source("CatalogueService", 2), source("DatasetMetadataRecord", 5)]));
    expect(lines.map(line => line.total)).toEqual([2, 5]);
    expect(lines.every(line => line.data.includes(2) || line.data.includes(5))).toBe(true);
    expect(lines.some(line => line.data.includes(7))).toBe(false);
  });

  it.each(["loading", "error", "partial", "unsupported"] as const)(
    "keeps a %s resource out of the chart instead of drawing it as zero", status => {
      const result = dashboardActivity([source("CatalogueService", 5), {
        resource: "DatasetMetadataRecord", statistics: { status },
      }]);
      if (result.status !== "ready") throw Error("the verified resource must still be drawn");
      expect(result.series.map(line => line.resource)).toEqual(["CatalogueService"]);
      expect(result.unavailable).toEqual([{ resource: "DatasetMetadataRecord", status }]);
    });

  it.each(["loading", "error", "partial", "unsupported"] as const)(
    "answers %s when no resource can be drawn", status => {
      expect(dashboardActivity([
        { resource: "CatalogueService", statistics: { status } },
        { resource: "DatasetMetadataRecord", statistics: { status } },
      ])).toEqual({ status });
    });

  it("answers the most severe status of all when nothing can be drawn", () => {
    expect(dashboardActivity([
      { resource: "CatalogueService", statistics: { status: "unsupported" } },
      { resource: "DatasetMetadataRecord", statistics: { status: "error" } },
      { resource: "ServiceMetadataRecord", statistics: { status: "loading" } },
    ])).toEqual({ status: "error" });
  });

  it("distinguishes zero events from missing coverage", () => {
    const result = dashboardActivity([source("CatalogueService", 0)]);
    if (result.status !== "ready") throw Error("a verified zero is a line");
    expect(result.series).toEqual([{ resource: "CatalogueService", data: [0, 0, 0, 0, 0, 0, 0], total: 0 }]);
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
