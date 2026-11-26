import { useState } from "react";
import { useLocaleState, useTranslate } from "react-admin";

import { Alert, Box, Checkbox, FormControlLabel, FormGroup, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { LineChart } from "@mui/x-charts/LineChart";

import SimpleCard from "../../MUI/SimpleCard";
import { activitySeries, dashboardActivity, type ActivityStatistics } from "../dashboardActivity";
import { hasDashboardHistory, type DashboardPeriod } from "../dashboardStatistics";
import { useDashboardActivity } from "../useDashboardActivity";

const stateMessages = {
  loading: "historyChart.asking",
  error: "historyChart.error",
  partial: "historyChart.partial",
  unsupported: "historyChart.noStatistics",
};

const ActivityPlot = ({ statistics }: { statistics: ActivityStatistics }) => {
  const translate = useTranslate();
  const [locale] = useLocaleState();
  const theme = useTheme();
  const [visible, setVisible] = useState<string[]>([...activitySeries]);
  const numbers = new Intl.NumberFormat(locale);
  const dates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const formatDay = (day: string) => dates.format(new Date(`${day}T00:00:00Z`));
  const colors = { new: theme.palette.success.main, updated: theme.palette.info.main, deleted: theme.palette.error.main };
  if (statistics.status !== "ready") {
    return <Alert severity="info" role="status">{translate(stateMessages[statistics.status])}</Alert>;
  }
  const { days, totals } = statistics;
  const series = activitySeries.filter(key => visible.includes(key)).map(key => ({
    id: key, label: translate(`historyChart.${key}`), data: days.map(day => day[key]),
    curve: "linear" as const, showMark: false, color: colors[key],
    valueFormatter: (value: number | null) => numbers.format(value ?? 0),
  }));
  return (
    <Stack spacing={1}>
      <Typography variant="body2">
        {translate("dashboard.activity.window", { from: formatDay(days[0].id), to: formatDay(days[days.length - 1].id), days: days.length })}
      </Typography>
      <Box component="dl" aria-label={translate("dashboard.activity.totals")} sx={{ display: "flex", flexWrap: "wrap", gap: 3, m: 0 }}>
        {activitySeries.map(key => <Box key={key}>
          <Typography component="dt" variant="body2">{translate(`historyChart.${key}`)}</Typography>
          <Typography component="dd" variant="h6" sx={{ m: 0 }}>{numbers.format(totals[key])}</Typography>
        </Box>)}
      </Box>
      <FormGroup row aria-label={translate("dashboard.activity.series")}>
        {activitySeries.map(key => <FormControlLabel key={key} label={translate(`historyChart.${key}`)} control={
          <Checkbox checked={visible.includes(key)} onChange={(_, checked) => setVisible(previous =>
            checked ? [...previous, key] : previous.filter(value => value !== key))} />
        } />)}
      </FormGroup>
      {activitySeries.every(key => totals[key] === 0) && <Typography>{translate("dashboard.activity.empty")}</Typography>}
      {series.length ? <LineChart
        aria-label={translate("dashboard.activity.title")}
        height={320}
        series={series}
        xAxis={[{ scaleType: "point", data: days.map(day => day.id), valueFormatter: formatDay }]}
        yAxis={[{ min: 0, tickMinStep: 1, valueFormatter: (value: number) => numbers.format(value), label: translate("dashboard.activity.events") }]}
        grid={{ horizontal: true }}
        skipAnimation
      /> : <Typography role="status">{translate("dashboard.activity.noSeries")}</Typography>}
    </Stack>
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
  const resourceName = (resource: string) => translate(`resources.${resource}.plural`, {
    _: translate(`resources.${resource}.name`, { _: resource }),
  });
  const excluded = resources.filter(resource => !hasDashboardHistory(resource));
  return (
    <SimpleCard title={translate("dashboard.activity.title")} subheader={translate("dashboard.activity.scope")} cardProps={{ sx: { minWidth: 0 } }}>
      <Stack spacing={2}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
          <TextField select label={translate("dashboard.activity.resource")} value={selection} onChange={event => setSelected(event.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="all">{translate("dashboard.activity.all")}</MenuItem>
            {sources.map(source => <MenuItem key={source.resource} value={source.resource}>{resourceName(source.resource)}</MenuItem>)}
          </TextField>
          <TextField select label={translate("dashboard.activity.period")} value={period} onChange={event => setPeriod(Number(event.target.value) as DashboardPeriod)}>
            {[7, 30, 90].map(days => <MenuItem key={days} value={days}>{translate("dashboard.activity.days", { days })}</MenuItem>)}
          </TextField>
        </Stack>
        <Box aria-label={translate("dashboard.activity.coverage")}>
          {selectedSources.map(source => <Typography key={source.resource} variant="body2">
            {resourceName(source.resource)}: {translate(source.statistics.status === "ready" ? "dashboard.activity.complete" : stateMessages[source.statistics.status])}
          </Typography>)}
          {excluded.length > 0 && <Typography variant="body2" color="text.secondary">
            {translate("dashboard.activity.excluded", { resources: excluded.map(resourceName).join(", ") })}
          </Typography>}
        </Box>
        <ActivityPlot statistics={statistics} />
      </Stack>
    </SimpleCard>
  );
};

export default ActivityChart;
