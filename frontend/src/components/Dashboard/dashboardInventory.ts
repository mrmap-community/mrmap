import type { ActivityStatus } from "./dashboardActivity";
import type { DashboardDay, DashboardPeriod } from "./dashboardStatistics";

/**
 * The verified answers of the complementary charts of the dashboard (#1820).
 *
 * Both read the daily statistics the KPI cards (#1817) and the activity chart
 * (#1818) already verify, so the three of them never disagree about the same
 * day: an inventory is a stock, an activity is a number of audit events, and
 * neither of them is invented from the other one.
 */
export interface InventorySource {
  resource: string;
  /** `ready` only for a resource whose stock history is provable (#1817) */
  status: "ready" | ActivityStatus;
  /** the verified days of the window, oldest first, as yyyy-mm-dd */
  days?: DashboardDay[];
  /** the inventory the resource counts today */
  count?: number;
}

/** one line of the inventory chart: the verified stock of a single resource */
export interface InventorySeries {
  resource: string;
  /** the stock of every day of the window, oldest first */
  data: number[];
  /** the inventory the resource counts today, which closes the line */
  count: number;
}

/** a resource whose stock cannot be proved, which is never drawn as a line */
export interface InventoryGap {
  resource: string;
  status: ActivityStatus;
}

export type InventoryStatistics =
  | { status: ActivityStatus }
  | {
      status: "ready";
      /** the days the shared axis names, oldest first, as yyyy-mm-dd */
      days: string[];
      series: InventorySeries[];
      unavailable: InventoryGap[];
    };

/**
 * The inventory every verified resource counted over the window, one line each.
 *
 * A line is drawn from its own resource alone and only while that resource is
 * `ready`: a stock is never reconstructed from audit events, so a resource the
 * statistics cannot prove is reported as `unavailable` instead of being drawn
 * from the event totals. The lines share one axis, which is only honest while
 * every verified resource covers the same window; the chart then draws nothing
 * and says why.
 */
export const dashboardInventory = (sources: InventorySource[]): InventoryStatistics => {
  if (!sources.length) return { status: "unsupported" };
  const verified: InventorySource[] = [];
  const unavailable: InventoryGap[] = [];
  for (const source of sources) {
    if (source.status !== "ready") {
      unavailable.push({ resource: source.resource, status: source.status });
    } else if (!source.days || source.count === undefined
      || source.days.some(day => day.total === null)) {
      // a stock the statistics cannot prove is a gap and never a flat zero line:
      // `dashboardStatistics` answers `null` for the stock of a day whose
      // additions make the baseline ambiguous (#1817)
      unavailable.push({ resource: source.resource, status: "partial" });
    } else {
      verified.push(source);
    }
  }
  if (!verified.length) {
    const severe = (["error", "loading", "partial", "unsupported"] as const)
      .find(status => unavailable.some(gap => gap.status === status));
    return { status: severe ?? "unsupported" };
  }
  const days = verified[0].days?.map(day => day.id) ?? [];
  if (verified.some(source => source.days?.length !== days.length
    || source.days?.some((day, index) => day.id !== days[index]))) return { status: "partial" };
  const series = verified.map(source => ({
    resource: source.resource,
    data: source.days?.map(day => day.total ?? 0) ?? [],
    count: source.count ?? 0,
  }));
  return { status: "ready", days, series, unavailable };
};

/** one slice of the distribution donut */
export interface InventorySlice {
  resource: string;
  /** the registered resources of that kind today */
  count: number;
  /** their share of the circle the donut draws, which is the visible answer */
  percent: number;
}

/** a resource whose count today cannot be answered, which is never a zero slice */
export interface InventoryCountGap {
  resource: string;
  status: ActivityStatus;
}

/** what a resource answers about its own count today — the donut needs no history */
export interface InventoryCountSource {
  resource: string;
  status: "ready" | ActivityStatus;
  /** the registered resources of that kind today */
  count?: number;
}

export type InventoryDistribution =
  | { status: ActivityStatus }
  | {
      status: "ready";
      slices: InventorySlice[];
      /** the counts of all resources which answered, the real denominator */
      total: number;
      unavailable: InventoryCountGap[];
    };

/**
 * The share of every kind of registered resource of the deployment.
 *
 * The denominator is the sum of the counts which were actually answered — the
 * donut never claims a share of an inventory it could not count, so a resource
 * whose count is missing is named beside the circle instead of silently
 * enlarging the shares of the others. A percentage is always relative to the
 * circle which is drawn: a hidden slice is reported by the card, because the
 * shares of the remaining ones changed with it.
 */
export const dashboardDistribution = (sources: InventoryCountSource[]): InventoryDistribution => {
  if (!sources.length) return { status: "unsupported" };
  const counted: { resource: string; count: number }[] = [];
  const unavailable: InventoryCountGap[] = [];
  for (const source of sources) {
    if (source.status !== "ready") {
      unavailable.push({ resource: source.resource, status: source.status });
    } else if (source.count === undefined) {
      unavailable.push({ resource: source.resource, status: "partial" });
    } else {
      counted.push({ resource: source.resource, count: source.count });
    }
  }
  if (!counted.length) {
    const severe = (["error", "loading", "partial", "unsupported"] as const)
      .find(status => unavailable.some(gap => gap.status === status));
    return { status: severe ?? "unsupported" };
  }
  const total = counted.reduce((sum, entry) => sum + entry.count, 0);
  const slices = counted.map(entry => ({
    resource: entry.resource,
    count: entry.count,
    percent: total === 0 ? 0 : (100 * entry.count) / total,
  }));
  return { status: "ready", slices, total, unavailable };
};

/** one stacked bar of the daily changes chart */
export interface ChangesSeries {
  resource: string;
  /** additions + updates + deletions of every day of the window, oldest first */
  data: number[];
  /** the events of the whole window */
  total: number;
}

export type DailyChangesStatistics =
  | { status: ActivityStatus }
  | {
      status: "ready";
      /** the days the shared axis names, oldest first, as yyyy-mm-dd */
      days: string[];
      series: ChangesSeries[];
      unavailable: InventoryGap[];
      /** the events of every verified resource over the whole window */
      total: number;
    };

/**
 * The daily audit events of the verified resources, as one stacked bar per day.
 *
 * The numbers are the same totals the activity chart (#1818) draws and are
 * never computed differently here: one bar stacks the events of the resources
 * whose coverage is verified for the whole window, and a resource which cannot
 * answer is named by the card instead of being stacked as a zero. The bar of a
 * day is the sum of the events of that day, so it is an aggregate of audit
 * events and never a stock.
 */
export const dashboardDailyChanges = (
  sources: InventorySource[],
  period: DashboardPeriod,
): DailyChangesStatistics => {
  const activity = sources.filter(source => source.status === "ready" && source.days);
  const unavailable: InventoryGap[] = sources.flatMap(source =>
    source.status === "ready"
      ? source.days ? [] : [{ resource: source.resource, status: "partial" as const }]
      : [{ resource: source.resource, status: source.status }]);
  if (!activity.length) {
    const severe = (["error", "loading", "partial", "unsupported"] as const)
      .find(status => unavailable.some(gap => gap.status === status));
    return { status: severe ?? "unsupported" };
  }
  const days = activity[0].days?.map(day => day.id) ?? [];
  if (days.length !== period
    || activity.some(source => source.days?.length !== days.length
      || source.days?.some((day, index) => day.id !== days[index]))) return { status: "partial" };
  const series = activity.map(source => {
    const data = (source.days ?? []).map(day => day.new + day.updated + day.deleted);
    return {
      resource: source.resource,
      data,
      total: data.reduce((sum, events) => sum + events, 0),
    };
  });
  return {
    status: "ready",
    days,
    series,
    unavailable,
    total: series.reduce((sum, line) => sum + line.total, 0),
  };
};
