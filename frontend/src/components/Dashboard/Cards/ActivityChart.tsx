import { useTranslate } from "react-admin";

import QueryStatsIcon from "@mui/icons-material/QueryStats";
import { Box, Typography } from "@mui/material";

import { dashboardActivity, type ActivitySource, type ActivityStatistics } from "../dashboardActivity";
import { hasDashboardHistory, type DashboardPeriod } from "../dashboardStatistics";
import { useDashboardActivity } from "../useDashboardActivity";
import {
  ChartCard, Coverage, LinePlot, PlotState, STATE_MESSAGES, usePlotLocales, when,
} from "./ChartParts";

/**
 * The statistical scope, asked for and never permanently standing in the card.
 *
 * The icon is the compact form of the coverage: which resources are drawn, which
 * of them cannot answer and which are excluded because the deployment has no
 * verified history for them.
 */
const ActivityCoverage = ({ sources, statistics, excluded, resourceName }: {
  sources: ActivitySource[];
  statistics: ActivityStatistics;
  excluded: string[];
  resourceName: (resource: string) => string;
}) => {
  const translate = useTranslate();
  const { numbers, formatDay } = usePlotLocales();
  const label = translate("dashboard.activity.coverage");
  const totals = new Map(statistics.status === "ready"
    ? statistics.series.map(line => [line.resource, line.total] as const) : []);
  const days = statistics.status === "ready" ? statistics.days : undefined;
  return <Coverage label={label}>
    <Typography variant="body2" sx={{ my: 1 }}>{translate("dashboard.activity.scope")}</Typography>
    <Box component="ul" sx={{ pl: 2, my: 1 }}>
      {sources.map(source => <Typography component="li" variant="body2" key={source.resource}>
        {resourceName(source.resource)}:{" "}
        {translate(source.statistics.status === "ready" ? "dashboard.activity.complete" : STATE_MESSAGES[source.statistics.status])}
        {totals.has(source.resource) && ` — ${numbers.format(totals.get(source.resource) ?? 0)} ${translate("dashboard.activity.events")}`}
      </Typography>)}
    </Box>
    {days && <Typography variant="body2" color="text.secondary">
      {translate("dashboard.activity.window", {
        from: formatDay(days[0]),
        to: formatDay(days.at(-1) ?? ""),
        days: days.length,
      })}
    </Typography>}
    {excluded.length > 0 && <Typography variant="body2" color="text.secondary">
      {translate("dashboard.activity.excluded", { resources: excluded.map(resourceName).join(", ") })}
    </Typography>}
  </Coverage>;
};

const ActivityPlot = ({ statistics, resourceName }: {
  statistics: ActivityStatistics;
  resourceName: (resource: string) => string;
}) => {
  const translate = useTranslate();
  if (statistics.status !== "ready") return <PlotState status={statistics.status} />;
  const { days, series: verified, unavailable } = statistics;
  return <LinePlot
    title={translate("dashboard.activity.title")}
    yAxisLabel={translate("dashboard.activity.yAxis")}
    days={days}
    lines={verified}
    resourceName={resourceName}
    marks
    verticalGrid
    unavailable={when(unavailable.length > 0, translate("dashboard.activity.unavailable", {
      resources: unavailable.map(gap => resourceName(gap.resource)).join(", "),
    }))}
    empty={when(verified.every(line => line.total === 0), translate("dashboard.activity.empty"))}
  />;
};

/**
 * The audit events of the deployment over the shared period of the dashboard.
 *
 * The left half of the chart row of the mockup: one line per resource whose
 * history is verified, drawn with the events of that resource alone. The period
 * comes from the header of the screen (#1820), because the inventory line, the
 * stacked bars and the KPI tiles beside this card answer the very same window —
 * a local selector would let two cards of one screen name two different windows.
 */
const ActivityChart = ({ resources, period }: {
  resources: string[];
  period: DashboardPeriod;
}) => {
  const translate = useTranslate();
  const sources = useDashboardActivity(resources, period);
  const statistics = dashboardActivity(sources);
  const resourceName = (resource: string) => translate(`dashboard.activity.resourceNames.${resource}`, {
    _: translate(`resources.${resource}.plural`, { _: resource }),
  });
  const excluded = resources.filter(resource => !hasDashboardHistory(resource));
  return (
    <ChartCard
      icon={<QueryStatsIcon fontSize="small" color="primary" />}
      title={translate("dashboard.activity.title")}
      action={<ActivityCoverage sources={sources} statistics={statistics} excluded={excluded} resourceName={resourceName} />}
    >
      <ActivityPlot statistics={statistics} resourceName={resourceName} />
    </ChartCard>
  );
};

export default ActivityChart;
