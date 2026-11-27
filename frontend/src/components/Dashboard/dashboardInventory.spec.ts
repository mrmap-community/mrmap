import type { ActivityStatus } from "./dashboardActivity";

import { describe, expect, it } from "vitest";

import { dashboardActivity } from "./dashboardActivity";
import {
  dashboardDailyChanges,
  dashboardDistribution,
  dashboardInventory,
  type InventoryCountSource,
  type InventorySource,
} from "./dashboardInventory";
import { dashboardStatistics, type DashboardPeriod } from "./dashboardStatistics";

/**
 * The source of a resource whose stock is provable: no audit event of the
 * window, so every day of it carries `count` (`dashboardStatistics` only proves
 * a stock while the window holds no addition, #1817).
 */
const stock = (
  resource: string,
  count: number,
  period: DashboardPeriod = 7,
  today: string = "2026-04-01",
  verified: boolean = true,
): InventorySource => {
  const statistics = dashboardStatistics([], 0, count, period, today);
  if (statistics.status !== "ready") throw Error("the fixture is not verified");
  return {
    resource,
    status: verified ? "ready" : "partial",
    days: verified ? statistics.days : undefined,
    count: verified ? count : undefined,
  };
};

/** the source of one resource whose events of the last day are `events` */
const eventsOf = (
  resource: string,
  events: { added?: number; updated?: number; deleted?: number },
  period: DashboardPeriod = 7,
  today: string = "2026-04-01",
): InventorySource => {
  const statistics = dashboardStatistics([
    {
      id: today, day: today,
      new: events.added ?? 0, updated: events.updated ?? 0, deleted: events.deleted ?? 0,
    },
  ], 1, 100, period, today);
  if (statistics.status !== "ready") throw Error("fixture is not verified");
  return {
    resource,
    status: "ready",
    days: statistics.days,
    count: (events.added ?? 0) + (events.updated ?? 0) + (events.deleted ?? 0),
  };
};

const counted = (
  resource: string,
  count?: number,
  status?: "ready" | ActivityStatus,
): InventoryCountSource => ({
  resource,
  status: status ?? (count === undefined ? "partial" : "ready"),
  count,
});

/** the answer of a chart which verified something, or the reason it answered nothing */
const ready = <T extends { status: string }>(result: T, what: string): Extract<T, { status: "ready" }> => {
  if (result.status !== "ready") throw Error(`${what}: ${result.status}`);
  return result as Extract<T, { status: "ready" }>;
};

describe("dashboard inventory", () => {
  it("draws one stock line per verified resource, never the events of it", () => {
    const result = ready(dashboardInventory([
      stock("Layer", 41),
      stock("CatalogueService", 7),
    ]), "no lines");
    expect(result.days).toHaveLength(7);
    expect(result.days.at(-1)).toBe("2026-04-01");
    expect(result.series).toEqual([
      { resource: "Layer", data: [41, 41, 41, 41, 41, 41, 41], count: 41 },
      { resource: "CatalogueService", data: [7, 7, 7, 7, 7, 7, 7], count: 7 },
    ]);
  });

  it("never answers a stock of zero for a resource which cannot prove one", () => {
    const result = dashboardInventory([
      stock("Layer", 41),
      { resource: "FeatureType", status: "loading" },
    ]);
    const readyResult = ready(result, "no lines");
    expect(readyResult.series.map(line => line.resource)).toEqual(["Layer"]);
    expect(readyResult.unavailable).toEqual([{ resource: "FeatureType", status: "loading" }]);
    expect(readyResult.series.some(line => line.data.every(value => value === 0)))
      .toBe(false);
  });

  it("names a verified resource whose numbers are missing instead of drawing a flat line", () => {
    const result = ready(dashboardInventory([
      stock("Layer", 41),
      stock("FeatureType", 0, 7, "2026-04-01", false),
    ]), "no lines");
    expect(result.series.map(line => line.resource)).toEqual(["Layer"]);
    expect(result.unavailable).toEqual([{ resource: "FeatureType", status: "partial" }]);
  });

  it("answers the severe state of the whole card when no resource can be drawn", () => {
    expect(dashboardInventory([{ resource: "Layer", status: "error" }]).status).toBe("error");
    expect(dashboardInventory([{ resource: "Layer", status: "loading" }]).status).toBe("loading");
    expect(dashboardInventory([{ resource: "Layer", status: "partial" }]).status).toBe("partial");
    expect(dashboardInventory([]).status).toBe("unsupported");
  });

  it("answers partial when the resources verify different windows", () => {
    expect(dashboardInventory([
      stock("Layer", 41, 7, "2026-04-01"),
      stock("CatalogueService", 7, 7, "2026-03-31"),
    ]).status).toBe("partial");
  });
});

describe("dashboard daily changes", () => {
  it("stacks the verified resources of one day into one bar", () => {
    const sources = [
      eventsOf("Layer", { added: 1, updated: 2 }),
      eventsOf("CatalogueService", { added: 4, deleted: 5 }),
    ];
    const result = ready(dashboardDailyChanges(sources, 7), "no bars");
    expect(result.days).toHaveLength(7);
    expect(result.days.at(-1)).toBe("2026-04-01");
    expect(result.series).toEqual([
      { resource: "Layer", data: [0, 0, 0, 0, 0, 0, 3], total: 3 },
      { resource: "CatalogueService", data: [0, 0, 0, 0, 0, 0, 9], total: 9 },
    ]);
    expect(result.total).toBe(12);
  });

  it("answers the very totals the activity chart draws, never its own ones", () => {
    // the two charts read the same verified statistics of the same window, so
    // the day of a bar is the day of the line beside it (#1818)
    const rows = [
      { resource: "Layer", new: 1, updated: 2, deleted: 3 },
      { resource: "CatalogueService", new: 4, updated: 0, deleted: 5 },
    ];
    const statistics = rows.map(row => dashboardStatistics(
      [{ id: "2026-04-01", day: "2026-04-01", new: row.new, updated: row.updated, deleted: row.deleted }],
      1, row.new + row.updated + row.deleted, 7, "2026-04-01",
    ));
    const activity = ready(dashboardActivity(rows.map((row, index) => ({
      resource: row.resource, statistics: statistics[index],
    }))), "no lines");
    const sources: InventorySource[] = rows.map((row, index) => {
      const verified = statistics[index];
      if (verified.status !== "ready") throw Error("the fixture is not verified");
      return {
        resource: row.resource,
        status: "ready" as const,
        days: verified.days,
        count: row.new + row.updated + row.deleted,
      };
    });
    const stacked = ready(dashboardDailyChanges(sources, 7), "no bars");
    expect(stacked.series.map(line => line.data)).toEqual(activity.series.map(line => line.data));
    expect(stacked.total).toBe(activity.series.reduce((sum, line) => sum + line.total, 0));
  });

  it("names a resource which cannot answer instead of stacking it as a zero", () => {
    const sources = [
      eventsOf("Layer", { added: 3 }),
      { resource: "FeatureType", status: "error" as const },
    ];
    const result = ready(dashboardDailyChanges(sources, 7), "no bars");
    expect(result.series.map(line => line.resource)).toEqual(["Layer"]);
    expect(result.unavailable).toEqual([{ resource: "FeatureType", status: "error" }]);
  });

  it("answers the severe state of the whole card when no resource can be stacked", () => {
    expect(dashboardDailyChanges([{ resource: "Layer", status: "error" }], 7).status).toBe("error");
    expect(dashboardDailyChanges([], 7).status).toBe("unsupported");
  });
});

describe("dashboard distribution", () => {
  it("shares the registered resources of the kinds which answered", () => {
    const result = ready(dashboardDistribution([
      counted("Layer", 30),
      counted("CatalogueService", 10),
    ]), "no slices");
    expect(result.slices).toEqual([
      { resource: "Layer", count: 30, percent: 75 },
      { resource: "CatalogueService", count: 10, percent: 25 },
    ]);
    expect(result.total).toBe(40);
  });

  it("keeps the denominator the sum of the answered counts and names the missing one", () => {
    const result = ready(dashboardDistribution([
      counted("Layer", 30),
      counted("FeatureType"),
      counted("WebMapService", 0, "unsupported"),
    ]), "no slices");
    expect(result.slices).toEqual([{ resource: "Layer", count: 30, percent: 100 }]);
    expect(result.total).toBe(30);
    expect(result.unavailable).toEqual([
      { resource: "FeatureType", status: "partial" },
      { resource: "WebMapService", status: "unsupported" },
    ]);
  });

  it("answers an empty deployment as an empty circle and not as a failure", () => {
    const result = ready(dashboardDistribution([counted("Layer", 0)]), "no slices");
    expect(result.slices).toEqual([{ resource: "Layer", count: 0, percent: 0 }]);
    expect(result.total).toBe(0);
  });

  it("answers the severe state of the whole card when no count answered", () => {
    expect(dashboardDistribution([{ resource: "Layer", status: "loading" }]).status).toBe("loading");
    expect(dashboardDistribution([{ resource: "Layer", status: "error" }]).status).toBe("error");
    expect(dashboardDistribution([]).status).toBe("unsupported");
  });
});
