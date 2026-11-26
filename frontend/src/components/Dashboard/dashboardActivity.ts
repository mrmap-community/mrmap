import type { DashboardDay, DashboardStatistics } from "./dashboardStatistics";

/** what a resource answers about its own history — none of them is a count */
export type ActivityStatus = "loading" | "error" | "partial" | "unsupported";

export interface ActivitySource {
  resource: string;
  statistics: DashboardStatistics;
}

/** one line of the chart: the daily audit events of a single verified resource */
export interface ActivitySeries {
  resource: string;
  /** additions + updates + deletions of every day of the window, oldest first */
  data: number[];
  /** the events of the whole window */
  total: number;
}

/** a resource whose events could not be verified, which is never drawn as zero */
export interface ActivityGap {
  resource: string;
  status: ActivityStatus;
}

export type ActivityStatistics =
  | { status: ActivityStatus }
  | {
      status: "ready";
      /** the days the shared axis names, oldest first, as yyyy-mm-dd */
      days: string[];
      series: ActivitySeries[];
      unavailable: ActivityGap[];
    };

/** the answer of the card when not a single resource can be drawn */
const SEVERITY = ["error", "loading", "partial", "unsupported"] as const;

const mostSevere = (gaps: ActivityGap[]): ActivityStatus =>
  SEVERITY.find(status => gaps.some(gap => gap.status === status)) ?? "unsupported";

/**
 * The daily audit events of every resource whose history is verified, one line each.
 *
 * A line is drawn from its own resource alone: events are never summed across
 * resources, so a resource without verified coverage can neither inflate nor
 * flatten another one, and it is never drawn as a zero line either — it is
 * reported as `unavailable` instead. The lines share one axis, which is only
 * honest while every verified resource covers the same window; the chart then
 * draws nothing and says why.
 */
export const dashboardActivity = (sources: ActivitySource[]): ActivityStatistics => {
  if (!sources.length) return { status: "unsupported" };
  const verified: { resource: string; days: DashboardDay[] }[] = [];
  const unavailable: ActivityGap[] = [];
  for (const source of sources) {
    if (source.statistics.status === "ready") {
      verified.push({ resource: source.resource, days: source.statistics.days });
    } else {
      unavailable.push({ resource: source.resource, status: source.statistics.status });
    }
  }
  if (!verified.length) return { status: mostSevere(unavailable) };
  const days = verified[0].days.map(day => day.id);
  if (verified.some(source => source.days.length !== days.length
    || source.days.some((day, index) => day.id !== days[index]))) return { status: "partial" };
  const series = verified.map(source => {
    const data = source.days.map(day => day.new + day.updated + day.deleted);
    return { resource: source.resource, data, total: data.reduce((sum, events) => sum + events, 0) };
  });
  return { status: "ready", days, series, unavailable };
};
