import type { DashboardPeriod } from "../dashboardStatistics";

import { useState } from "react";
import { useLocaleState, useTranslate } from "react-admin";

import StackedBarChartIcon from "@mui/icons-material/StackedBarChart";
import { Box, Stack, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { BarChart } from "@mui/x-charts/BarChart";

import SimpleCard from "../../MUI/SimpleCard";
import { dashboardResourceColor } from "../dashboardColors";
import {
  dashboardDailyChanges,
  type DailyChangesStatistics,
  type InventorySource,
} from "../dashboardInventory";

/** the days of the window the axis names, so a 30 day window names eight of them */
const NAMED_DAYS = 8;

/** the height of the plot itself; the card stays within the middle row of the mockup */
const PLOT_HEIGHT = 132;

const tickStep = (days: number) => Math.max(1, Math.ceil((days - 1) / NAMED_DAYS));

/** the whole numbers the value axis counts in, never below one */
const valueStep = (max: number) => {
  const target = Math.max(1, max);
  const power = 10 ** Math.floor(Math.log10(target / 4));
  return [1, 2, 5, 10].map(multiplier => multiplier * power)
    .find(step => step >= 1 && Math.ceil(target / step) <= 4) ?? Math.max(1, 10 * power);
};

/**
 * The daily changes of the deployment, stacked by resource type.
 *
 * One bar answers the audit events of one day and stacks the resources whose
 * coverage is verified for the whole window: the totals are the ones of the
 * activity chart (#1818), drawn with the same colors and the same period, so a
 * day never reads differently in the two of them. The bar is an aggregate of
 * events and never a stock — the stock beside it is answered by the inventory
 * chart — and a resource which cannot answer is named instead of being stacked
 * as a zero.
 */
const DailyChangesChart = ({ sources, period }: {
  /** the verified sources of the dashboard, which the other cards share */
  sources: InventorySource[];
  period: DashboardPeriod;
}) => {
  const translate = useTranslate();
  const [locale] = useLocaleState();
  const theme = useTheme();
  const [hidden, setHidden] = useState<{ type: "bar"; seriesId: string }[]>([]);
  const statistics: DailyChangesStatistics = dashboardDailyChanges(sources, period);
  const numbers = new Intl.NumberFormat(locale);
  const dates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const shortDates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" });
  const resourceName = (resource: string) => translate(`dashboard.activity.resourceNames.${resource}`, {
    _: translate(`resources.${resource}.plural`, { _: resource }),
  });

  const body = () => {
    if (statistics.status !== "ready") {
      const messages = {
        loading: "historyChart.asking", error: "historyChart.error",
        partial: "historyChart.partial", unsupported: "historyChart.noStatistics",
      } as const;
      return <Typography variant="body2" role="status" sx={{ py: 1 }}>
        {translate(messages[statistics.status])}
      </Typography>;
    }
    const { days, series: verified, unavailable, total } = statistics;
    const stacked = verified.filter(line => !hidden.some(entry => entry.seriesId === line.resource));
    const maxValue = Math.max(1, ...days.map((_day, index) =>
      stacked.reduce((sum, line) => sum + (line.data[index] ?? 0), 0)));
    const step = valueStep(maxValue);
    const ticks = Array.from({ length: Math.ceil(maxValue / step) + 1 }, (_, index) => index * step);
    return <Box>
      <BarChart
        aria-label={translate("dashboard.changes.title")}
        height={PLOT_HEIGHT}
        series={verified.map(line => ({
          id: line.resource,
          label: resourceName(line.resource),
          data: line.data,
          stack: "events",
          color: dashboardResourceColor(theme, line.resource),
          valueFormatter: (value: number | null) => numbers.format(value ?? 0),
        }))}
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
          scaleType: "band", data: days, height: 22,
          valueFormatter: (day: string, context: { location: string }) =>
            context.location === "tick"
              ? shortDates.format(new Date(`${day}T00:00:00Z`))
              : dates.format(new Date(`${day}T00:00:00Z`)),
          tickInterval: (_day: string, index: number) => index % tickStep(days.length) === 0,
          tickLabelStyle: { fontSize: 11, fill: theme.palette.text.secondary },
        }]}
        yAxis={[{
          min: 0, max: ticks.at(-1), tickNumber: ticks.length, tickMinStep: 1, domainLimit: "strict", width: "auto",
          label: translate("dashboard.changes.yAxis"),
          labelStyle: { fontSize: 11, fontWeight: 600, fill: theme.palette.text.primary },
          tickLabelStyle: { fontSize: 11, fill: theme.palette.text.secondary },
          valueFormatter: (value: number) => numbers.format(value),
        }]}
        margin={{ left: 0, right: 8, top: 8, bottom: 0 }}
        grid={{ horizontal: true }}
        sx={{
          "& .MuiChartsGrid-line": { stroke: theme.palette.divider },
          "& .MuiBarElement": { stroke: theme.palette.background.paper, strokeWidth: 0.5 },
        }}
        skipAnimation
      />
      {stacked.length === 0 && <Typography variant="caption" role="status">
        {translate("dashboard.activity.noSeries")}
      </Typography>}
      {unavailable.length > 0 && <Typography variant="caption" color="warning.main" role="status">
        {translate("dashboard.activity.unavailable", { resources: unavailable.map(gap => resourceName(gap.resource)).join(", ") })}
      </Typography>}
      {statistics.status === "ready" && total === 0
        && <Typography variant="caption" role="status">{translate("dashboard.activity.empty")}</Typography>}
      {statistics.status === "ready" && total > 0 && <Typography variant="caption" color="text.secondary">
        {translate("dashboard.changes.total", { events: numbers.format(total), days: period })}
      </Typography>}
    </Box>;
  };

  return (
    <SimpleCard
      title={<Stack direction="row" useFlexGap sx={{ alignItems: "center", columnGap: 0.25, minWidth: 0 }}>
        <StackedBarChartIcon fontSize="small" color="primary" />
        <Typography component="h2" variant="subtitle2" sx={{ minWidth: 0 }} noWrap>
          {translate("dashboard.changes.title")}
        </Typography>
      </Stack>}
      subheader={<Typography variant="caption" color="text.secondary">
        {translate("dashboard.changes.scope", { days: period })}
      </Typography>}
      headerProps={{ sx: { alignItems: "flex-start", minHeight: 40, px: 1.5, py: 0.25 } }}
      cardProps={{ variant: "outlined", sx: { minWidth: 0, boxShadow: "none", borderRadius: 2, height: "100%" } }}
      contentProps={{ sx: { px: 0.5, pt: 0, pb: 0.5, "&:last-child": { pb: 0.5 } } }}
      divider={false}
    >
      {body()}
    </SimpleCard>
  );
};

export default DailyChangesChart;
