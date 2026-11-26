import { describe, expect, it } from "vitest";

import { dashboardStatistics, dashboardToday, hasDashboardHistory } from "./dashboardStatistics";

const end = "2026-04-01";
const row = (day: string, added = 0, updated = 0, deleted = 0) =>
  ({ id: day, day, new: added, updated, deleted });

describe("dashboard statistics", () => {
  it.each([7, 30, 90] as const)("covers %i days including today across the DST boundary", period => {
    const result = dashboardStatistics([row(end, 0, 2, 1)], 1, 9, period, end);
    expect(result.status).toBe("ready");
    if (result.status !== "ready") throw Error("missing window");
    expect(result.days).toHaveLength(period);
    expect(result.days.at(-1)).toEqual({ id: end, new: 0, updated: 2, deleted: 1, total: 9 });
    expect(result.days[0].id).toBe(({ 7: "2026-03-26", 30: "2026-03-03", 90: "2026-01-02" })[period]);
    expect(result.days[0].total).toBe(10);
    expect(result.inventory).toEqual({ baseline: 10, delta: -1, percent: -10 });
  });

  it("uses the persisted Berlin day on both sides of the clock change", () => {
    expect(dashboardToday(new Date("2026-03-28T23:30:00Z"))).toBe("2026-03-29");
    expect(dashboardToday(new Date("2026-03-29T22:30:00Z"))).toBe("2026-03-30");
  });

  it("only fills missing days once the page reaches the window or exhausts the list", () => {
    expect(dashboardStatistics([row(end)], 3, 1, 7, end).status).toBe("partial");
    expect(dashboardStatistics([row("2026-03-26")], 3, 1, 7, end).status).toBe("ready");
    expect(dashboardStatistics([], undefined, 0, 7, end).status).toBe("partial");
    expect(dashboardStatistics([], 0, undefined, 7, end).status).toBe("partial");
    expect(dashboardStatistics([], 0, 0, 7, end)).toMatchObject({
      status: "ready", inventory: { baseline: 0, delta: 0, percent: null },
    });
  });

  it("retains additions as events when a first-seen edit could be counted as new", () => {
    const result = dashboardStatistics([row(end, 3)], 1, 5, 7, end);
    expect(result).toMatchObject({ status: "ready", inventory: null });
    if (result.status === "ready") expect(result.days.at(-1)).toMatchObject({ new: 3, total: null });
  });

  it("refuses duplicate, unsorted, future and malformed rows", () => {
    for (const rows of [[row(end), row(end)], [row("2026-03-31"), row(end)],
      [row("2026-04-02")], [row(end, -1)]]) {
      expect(dashboardStatistics(rows, rows.length, 1, 30, end).status).toBe("partial");
    }
  });

  it("limits history to matching count and audit scopes", () => {
    for (const resource of ["User", "Organization", "WebMapService", "WebFeatureService", "Layer", "FeatureType"]) {
      expect(hasDashboardHistory(resource)).toBe(false);
    }
    for (const resource of ["CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord"]) {
      expect(hasDashboardHistory(resource)).toBe(true);
    }
  });
});
