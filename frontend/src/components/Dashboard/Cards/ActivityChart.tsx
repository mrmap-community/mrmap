import type { VisibilityIdentifierWithType } from "@mui/x-charts/plugins";

import type { ReactNode } from "react";
import { useId, useState } from "react";
import { useLocaleState, useTranslate } from "react-admin";

import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { Alert, Box, IconButton, MenuItem, Popover, Stack, TextField, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { ChartsLegend, type ChartsLegendProps } from "@mui/x-charts/ChartsLegend";
import { LineChart } from "@mui/x-charts/LineChart";

import SimpleCard from "../../MUI/SimpleCard";
import { activitySeries, dashboardActivity, type ActivitySource, type ActivityStatistics } from "../dashboardActivity";
import { hasDashboardHistory, type DashboardPeriod } from "../dashboardStatistics";
import { useDashboardActivity } from "../useDashboardActivity";

const stateSeverity = { loading: "info", error: "error", partial: "warning", unsupported: "info" } as const;

const stateMessages = {
  loading: "historyChart.asking",
  error: "historyChart.error",
  partial: "historyChart.partial",
  unsupported: "historyChart.noStatistics",
};

/** Keep the native interactive legend and the selectors in one wrapping toolbar. */
const ActivityLegend = ({ controls, ...props }: ChartsLegendProps & { controls?: ReactNode }) => (
  <Stack direction="row" useFlexGap sx={{ gridArea: "legend", alignItems: "center", flexWrap: "wrap", gap: 1, mb: 1, minWidth: 0 }}>
    {controls}
    <Box sx={{ ml: { sm: "auto" }, minWidth: 0 }}><ChartsLegend {...props} /></Box>
  </Stack>
);

const ActivityCoverage = ({ sources, excluded, resourceName }: {
  sources: ActivitySource[];
  excluded: string[];
  resourceName: (resource: string) => string;
}) => {
  const translate = useTranslate();
  const id = useId();
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
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
          {resourceName(source.resource)}: {translate(source.statistics.status === "ready" ? "dashboard.activity.complete" : stateMessages[source.statistics.status])}
        </Typography>)}
      </Box>
      {excluded.length > 0 && <Typography variant="body2" color="text.secondary">
        {translate("dashboard.activity.excluded", { resources: excluded.map(resourceName).join(", ") })}
      </Typography>}
    </Popover>
  </>;
};

const ActivityPlot = ({ statistics, controls }: { statistics: ActivityStatistics; controls: ReactNode }) => {
  const translate = useTranslate();
  const [locale] = useLocaleState();
  const theme = useTheme();
  const [hidden, setHidden] = useState<VisibilityIdentifierWithType<"line">[]>([]);
  const numbers = new Intl.NumberFormat(locale);
  const compactNumbers = new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 });
  const dates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const shortDates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" });
  const formatDay = (day: string) => dates.format(new Date(`${day}T00:00:00Z`));
  const formatShortDay = (day: string) => shortDates.format(new Date(`${day}T00:00:00Z`));
  const colors = { new: theme.palette.success.main, updated: theme.palette.info.main, deleted: theme.palette.error.main };
  if (statistics.status !== "ready") {
    return <Stack spacing={1}>
      {controls}
      <Alert severity={stateSeverity[statistics.status]} role="status">
        {translate(stateMessages[statistics.status])}
      </Alert>
    </Stack>;
  }
  const { days, totals } = statistics;
  const series = activitySeries.map(key => ({
    id: key, label: translate(`historyChart.${key}`), data: days.map(day => day[key]),
    curve: "linear" as const, showMark: false, color: colors[key],
    valueFormatter: (value: number | null) => numbers.format(value ?? 0),
  }));
  const legend: ChartsLegendProps & { controls: ReactNode } = {
    controls,
    toggleVisibilityOnClick: true,
    sx: { flexWrap: "wrap", gap: 1.5, fontSize: "0.75rem" },
  };
  return (
    <Box>
      {hidden.length === activitySeries.length && <Typography variant="caption" role="status">{translate("dashboard.activity.noSeries")}</Typography>}
      <LineChart
        aria-label={translate("dashboard.activity.title")}
        height={230}
        series={series}
        hiddenItems={hidden}
        onHiddenItemsChange={setHidden}
        slots={{ legend: ActivityLegend }}
        slotProps={{ legend }}
        xAxis={[{
          scaleType: "point", data: days.map(day => day.id), height: 28,
          valueFormatter: (day: string, context: { location: string }) => context.location === "tick" ? formatShortDay(day) : formatDay(day),
          tickInterval: (_day: string, index: number) => index % Math.ceil((days.length - 1) / 4) === 0 || index === days.length - 1,
        }]}
        yAxis={[{
          min: 0, tickMinStep: 1, width: 80,
          valueFormatter: (value: number) => compactNumbers.format(value),
        }]}
        margin={{ left: 0, right: 32, top: 12, bottom: 0 }}
        grid={{ horizontal: true }}
        sx={{ "& .MuiChartsGrid-line": { stroke: theme.palette.divider, strokeDasharray: "3 3" } }}
        skipAnimation
      />
      <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", alignItems: "baseline", columnGap: 2, rowGap: 0.5 }}>
        <Typography variant="caption" color="text.secondary" title={translate("dashboard.activity.window", { from: formatDay(days[0].id), to: formatDay(days[days.length - 1].id), days: days.length })}>
          {formatShortDay(days[0].id)} – {formatShortDay(days[days.length - 1].id)}
        </Typography>
        <Box component="dl" aria-label={translate("dashboard.activity.totals")} sx={{ display: "flex", flexWrap: "wrap", gap: 2, m: 0 }}>
          {activitySeries.map(key => <Box key={key} sx={{ display: "flex", gap: 0.5 }}>
            <Typography component="dt" variant="caption" color="text.secondary">{translate(`historyChart.${key}`)}</Typography>
            <Typography component="dd" variant="caption" sx={{ m: 0, fontWeight: 600 }}>{numbers.format(totals[key])}</Typography>
          </Box>)}
        </Box>
        {activitySeries.every(key => totals[key] === 0) && <Typography variant="caption">{translate("dashboard.activity.empty")}</Typography>}
      </Stack>
    </Box>
  );
};

const ActivityChart = ({ resources }: { resources: string[] }) => {
  const translate = useTranslate();
  const [period, setPeriod] = useState<DashboardPeriod>(30);
  const [selected, setSelected] = useState("all");
  const sources = useDashboardActivity(resources, period);
  // Permission changes must never leave a previously selected resource visible.
  const selection = sources.some(source => source.resource === selected) ? selected : "all";
  const selectedSources = sources.filter(source => selection === "all" || source.resource === selection);
  const statistics = dashboardActivity(selectedSources);
  const resourceName = (resource: string) => translate(`dashboard.activity.resourceNames.${resource}`, {
    _: translate(`resources.${resource}.plural`, { _: resource }),
  });
  const excluded = resources.filter(resource => !hasDashboardHistory(resource));
  const controls = <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1, minWidth: 0 }}>
    <TextField select size="small" label={translate("dashboard.activity.resource")} value={selection} onChange={event => setSelected(event.target.value)} sx={{ minWidth: 160, maxWidth: "100%" }}>
      <MenuItem value="all">{translate("dashboard.activity.all")}</MenuItem>
      {sources.map(source => <MenuItem key={source.resource} value={source.resource}>{resourceName(source.resource)}</MenuItem>)}
    </TextField>
    <TextField select size="small" label={translate("dashboard.activity.period")} value={period} onChange={event => setPeriod(Number(event.target.value) as DashboardPeriod)}>
      {[7, 30, 90].map(days => <MenuItem key={days} value={days}>{translate("dashboard.activity.days", { days })}</MenuItem>)}
    </TextField>
  </Stack>;
  return (
    <SimpleCard
      title={<Typography component="h2" variant="subtitle2">{translate("dashboard.activity.title")}</Typography>}
      subheader={translate("dashboard.activity.coverageSummary", {
        ready: selectedSources.filter(source => source.statistics.status === "ready").length,
        total: selectedSources.length, excluded: excluded.length,
      })}
      headerProps={{
        sx: { px: 2, py: 1.25 },
        action: <ActivityCoverage sources={selectedSources} excluded={excluded} resourceName={resourceName} />,
        slotProps: { subheader: { variant: "caption" } },
      }}
      cardProps={{ variant: "outlined", sx: { minWidth: 0, boxShadow: "none", borderRadius: 2 } }}
      contentProps={{ sx: { px: 2, pt: 0, "&:last-child": { pb: 1.5 } } }}
      divider={false}
    >
      <ActivityPlot statistics={statistics} controls={controls} />
    </SimpleCard>
  );
};

export default ActivityChart;
