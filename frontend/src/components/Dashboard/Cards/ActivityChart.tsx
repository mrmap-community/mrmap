import type { VisibilityIdentifierWithType } from "@mui/x-charts/plugins";

import { useId, useState } from "react";
import { useLocaleState, useTranslate } from "react-admin";

import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import QueryStatsIcon from "@mui/icons-material/QueryStats";
import { Alert, Box, IconButton, Popover, Stack, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { LineChart } from "@mui/x-charts/LineChart";

import SimpleCard from "../../MUI/SimpleCard";
import { dashboardActivity, type ActivitySource, type ActivityStatistics } from "../dashboardActivity";
import { dashboardResourceColor } from "../dashboardColors";
import { hasDashboardHistory, type DashboardPeriod } from "../dashboardStatistics";
import { useDashboardActivity } from "../useDashboardActivity";

const stateSeverity = { loading: "info", error: "error", partial: "warning", unsupported: "info" } as const;

const stateMessages = {
  loading: "historyChart.asking",
  error: "historyChart.error",
  partial: "historyChart.partial",
  unsupported: "historyChart.noStatistics",
};

/** the days of the window the axis names, so a 30 day window names ten of them */
const NAMED_DAYS = 10;

/** the height of the plot itself; the card stays within the chart row of the mockup */
const PLOT_HEIGHT = 168;

const tickStep = (days: number) => Math.max(1, Math.ceil((days - 1) / NAMED_DAYS));

/** the whole numbers the value axis of the chart counts in, never below one */
const valueStep = (max: number) => {
  const target = Math.max(1, max);
  const power = 10 ** Math.floor(Math.log10(target / 4));
  return [1, 2, 5, 10].map(multiplier => multiplier * power)
    .find(step => step >= 1 && Math.ceil(target / step) <= 5) ?? Math.max(1, 10 * power);
};

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
  const [locale] = useLocaleState();
  const id = useId();
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const numbers = new Intl.NumberFormat(locale);
  const dates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const totals = new Map(statistics.status === "ready"
    ? statistics.series.map(line => [line.resource, line.total] as const) : []);
  const days = statistics.status === "ready" ? statistics.days : undefined;
  return <>
    <Tooltip title={translate("dashboard.activity.coverage")}>
      <IconButton size="small" aria-label={translate("dashboard.activity.coverage")}
        aria-haspopup="dialog" aria-expanded={Boolean(anchor)} aria-controls={anchor ? id : undefined}
        onClick={event => setAnchor(event.currentTarget)}>
        <InfoOutlinedIcon fontSize="small" />
      </IconButton>
    </Tooltip>
    <Popover id={id} open={Boolean(anchor)} anchorEl={anchor} onClose={() => setAnchor(null)}
      anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}
      slotProps={{ paper: { role: "dialog", "aria-label": translate("dashboard.activity.coverage"), sx: { p: 2, width: 360, maxWidth: "calc(100% - 32px)" } } }}>
      <Typography variant="subtitle2" component="h3">{translate("dashboard.activity.coverage")}</Typography>
      <Typography variant="body2" sx={{ my: 1 }}>{translate("dashboard.activity.scope")}</Typography>
      <Box component="ul" sx={{ pl: 2, my: 1 }}>
        {sources.map(source => <Typography component="li" variant="body2" key={source.resource}>
          {resourceName(source.resource)}:{" "}
          {translate(source.statistics.status === "ready" ? "dashboard.activity.complete" : stateMessages[source.statistics.status])}
          {totals.has(source.resource) && ` — ${numbers.format(totals.get(source.resource) ?? 0)} ${translate("dashboard.activity.events")}`}
        </Typography>)}
      </Box>
      {days && <Typography variant="body2" color="text.secondary">
        {translate("dashboard.activity.window", {
          from: dates.format(new Date(`${days[0]}T00:00:00Z`)),
          to: dates.format(new Date(`${days.at(-1) ?? ""}T00:00:00Z`)),
          days: days.length,
        })}
      </Typography>}
      {excluded.length > 0 && <Typography variant="body2" color="text.secondary">
        {translate("dashboard.activity.excluded", { resources: excluded.map(resourceName).join(", ") })}
      </Typography>}
    </Popover>
  </>;
};

const ActivityPlot = ({ statistics, resourceName }: {
  statistics: ActivityStatistics;
  resourceName: (resource: string) => string;
}) => {
  const translate = useTranslate();
  const [locale] = useLocaleState();
  const theme = useTheme();
  const [hidden, setHidden] = useState<VisibilityIdentifierWithType<"line">[]>([]);
  const numbers = new Intl.NumberFormat(locale);
  const dates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const shortDates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" });
  const formatDay = (day: string) => dates.format(new Date(`${day}T00:00:00Z`));
  const formatShortDay = (day: string) => shortDates.format(new Date(`${day}T00:00:00Z`));
  if (statistics.status !== "ready") {
    return <Alert severity={stateSeverity[statistics.status]} role="status" sx={{ my: 1 }}>
      {translate(stateMessages[statistics.status])}
    </Alert>;
  }
  const { days, series: verified, unavailable } = statistics;
  const maxValue = Math.max(1, ...verified.flatMap(line => line.data));
  const step = valueStep(maxValue);
  const ticks = Array.from({ length: Math.ceil(maxValue / step) + 1 }, (_, index) => index * step);
  const series = verified.map(line => ({
    id: line.resource,
    label: resourceName(line.resource),
    data: line.data,
    curve: "linear" as const,
    area: true,
    showMark: true,
    shape: "circle" as const,
    color: dashboardResourceColor(theme, line.resource),
    valueFormatter: (value: number | null) => numbers.format(value ?? 0),
  }));
  return <Box>
    {hidden.length === series.length && series.length > 0
      && <Typography variant="caption" role="status">{translate("dashboard.activity.noSeries")}</Typography>}
    <LineChart
      aria-label={translate("dashboard.activity.title")}
      height={PLOT_HEIGHT}
      series={series}
      hiddenItems={hidden}
      onHiddenItemsChange={setHidden}
      slotProps={{
        legend: {
          direction: "horizontal",
          toggleVisibilityOnClick: true,
          sx: { justifyContent: "center", columnGap: 2, rowGap: 0.25, fontSize: "0.75rem", minHeight: 24 },
        },
      }}
      xAxis={[{
        scaleType: "point", data: days, height: 24,
        valueFormatter: (day: string, context: { location: string }) =>
          context.location === "tick" ? formatShortDay(day) : formatDay(day),
        tickInterval: (_day: string, index: number) => index % tickStep(days.length) === 0,
        tickLabelStyle: { fontSize: 11, fill: theme.palette.text.secondary },
      }]}
      yAxis={[{
        min: 0, max: ticks.at(-1), tickNumber: ticks.length, tickMinStep: 1, domainLimit: "strict", width: "auto",
        label: translate("dashboard.activity.yAxis"),
        labelStyle: { fontSize: 11, fontWeight: 600, fill: theme.palette.text.primary },
        tickLabelStyle: { fontSize: 11, fill: theme.palette.text.secondary },
        valueFormatter: (value: number) => numbers.format(value),
      }]}
      margin={{ left: 0, right: 26, top: 8, bottom: 0 }}
      grid={{ horizontal: true, vertical: true }}
      sx={{
        "& .MuiChartsGrid-line": { stroke: theme.palette.divider },
        "& .MuiLineChart-area": { fillOpacity: 0.12 },
        "& .MuiLineChart-mark": { stroke: theme.palette.background.paper, strokeWidth: 1 },
      }}
      skipAnimation
    />
    {unavailable.length > 0 && <Typography variant="caption" color="warning.main" role="status">
      {translate("dashboard.activity.unavailable", { resources: unavailable.map(gap => resourceName(gap.resource)).join(", ") })}
    </Typography>}
    {verified.every(line => line.total === 0) && <Typography variant="caption" role="status">
      {translate("dashboard.activity.empty")}
    </Typography>}
  </Box>;
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
    <SimpleCard
      title={<Stack direction="row" useFlexGap sx={{ alignItems: "center", columnGap: 0.25, minWidth: 0 }}>
        <QueryStatsIcon fontSize="small" color="primary" />
        <Typography component="h2" variant="subtitle2" sx={{ minWidth: 0 }} noWrap>
          {translate("dashboard.activity.title")}
        </Typography>
        <ActivityCoverage sources={sources} statistics={statistics} excluded={excluded} resourceName={resourceName} />
      </Stack>}
      headerProps={{ sx: { alignItems: "center", minHeight: 40, px: 1.5, py: 0.25 } }}
      cardProps={{ variant: "outlined", sx: { minWidth: 0, boxShadow: "none", borderRadius: 2 } }}
      contentProps={{ sx: { px: 0.5, pt: 0, pb: 0.5, "&:last-child": { pb: 0.5 } } }}
      divider={false}
    >
      <ActivityPlot statistics={statistics} resourceName={resourceName} />
    </SimpleCard>
  );
};

export default ActivityChart;
