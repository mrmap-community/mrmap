import type { RaRecord } from "react-admin";

import { changesOfDays, type DailyChange } from "../Resource/Generic/History/historyDays";

export type DashboardPeriod = 7 | 30 | 90;
export type DashboardDay = Omit<DailyChange, "total"> & { total: number | null };
export type DashboardStatistics =
  | { status: "loading" | "unsupported" | "partial" | "error" }
  | {
      status: "ready";
      days: DashboardDay[];
      inventory: { baseline: number; delta: number; percent: number | null } | null;
    };

// These three inventory lists have the same deployment-wide scope as their audit totals.
export const hasDashboardHistory = (resource: string) =>
  ["CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord"].includes(resource);

const berlinDate = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Berlin", year: "numeric", month: "2-digit", day: "2-digit",
});

export const dashboardToday = (now = new Date()) => berlinDate.format(now);

const isCount = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

export const dashboardStatistics = (
  rows: RaRecord[], rowCount: number | undefined, count: number | undefined,
  period: DashboardPeriod, today: string,
): DashboardStatistics => {
  // Step through calendar labels independently of DST and the browser's time zone.
  const end = Date.parse(today + "T00:00:00Z");
  const days = Array.from({ length: period }, (_, i) =>
    new Date(end - (period - 1 - i) * 86400000).toISOString().slice(0, 10));

  if (!isCount(rowCount) || rows.length > rowCount || !isCount(count)) return { status: "partial" };
  let previous: string | undefined;
  for (const row of rows) {
    if (typeof row.day !== "string" || row.day !== row.id ||
        !/^\d{4}-\d{2}-\d{2}$/.test(row.day) || row.day > today ||
        (previous !== undefined && row.day >= previous) ||
        ![row.new, row.updated, row.deleted].every(isCount)) return { status: "partial" };
    previous = row.day;
  }
  // A capped first page suffices when its oldest day reaches the start of the window.
  if (rows.length < rowCount && (!previous || previous > days[0])) return { status: "partial" };

  const changes = changesOfDays(rows, count, days);
  // "new" includes first-seen edits of pre-existing records. An addition in this
  // window makes a stock baseline ambiguous even when coverage is complete.
  if (changes.some(day => day.new > 0)) {
    return { status: "ready", days: changes.map(day => ({ ...day, total: null })), inventory: null };
  }
  const first = changes[0];
  const baseline = first.total + first.deleted;
  const delta = count - baseline;
  return { status: "ready", days: changes, inventory: {
    baseline, delta, percent: baseline === 0 ? null : 100 * delta / baseline,
  } };
};
