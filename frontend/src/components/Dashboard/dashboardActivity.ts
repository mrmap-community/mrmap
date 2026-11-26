import type { DashboardStatistics } from "./dashboardStatistics";

export const activitySeries = ["new", "updated", "deleted"] as const;
export type ActivitySeries = typeof activitySeries[number];
export type ActivityDay = { id: string } & Record<ActivitySeries, number>;
export interface ActivitySource {
  resource: string;
  statistics: DashboardStatistics;
}
export type ActivityStatistics =
  | { status: "loading" | "error" | "partial" | "unsupported" }
  | { status: "ready"; days: ActivityDay[]; totals: Record<ActivitySeries, number> };

/** Aggregate events only when every selected resource covers the same full window. */
export const dashboardActivity = (sources: ActivitySource[]): ActivityStatistics => {
  if (!sources.length) return { status: "unsupported" };
  for (const status of ["error", "loading", "partial", "unsupported"] as const) {
    if (sources.some(source => source.statistics.status === status)) return { status };
  }
  const ready = sources.flatMap(source => source.statistics.status === "ready" ? [source.statistics.days] : []);
  const labels = ready[0].map(day => day.id);
  if (ready.some(days => days.length !== labels.length || days.some((day, i) => day.id !== labels[i]))) {
    return { status: "partial" };
  }
  const days = labels.map((id, i) => ({
    id,
    new: ready.reduce((sum, resource) => sum + resource[i].new, 0),
    updated: ready.reduce((sum, resource) => sum + resource[i].updated, 0),
    deleted: ready.reduce((sum, resource) => sum + resource[i].deleted, 0),
  }));
  const totals = { new: 0, updated: 0, deleted: 0 };
  for (const day of days) for (const key of activitySeries) totals[key] += day[key];
  return { status: "ready", days, totals };
};
