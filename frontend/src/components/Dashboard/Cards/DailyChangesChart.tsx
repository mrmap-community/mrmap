import type { DashboardPeriod } from "../dashboardStatistics";

import { useState } from "react";
import { useTranslate } from "react-admin";

import StackedBarChartIcon from "@mui/icons-material/StackedBarChart";
import { Box, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { BarChart } from "@mui/x-charts/BarChart";

import { dashboardResourceColor } from "../dashboardColors";
import {
  dashboardDailyChanges,
  type DailyChangesStatistics,
  type InventorySource,
} from "../dashboardInventory";
import { ChartCard, countAxis, dayAxis, plotLegend, PlotState, usePlotLocales } from "./ChartParts";

/** the days of the window the axis names, so a 30 day window names eight of them */
const NAMED_DAYS = 8;

/** the height of the plot itself; the card stays within the middle row of the mockup */
const PLOT_HEIGHT = 132;

/** the labels of the value axis this row of the mockup can read beside its bars */
const VALUE_TICKS = 4;

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
  const theme = useTheme();
  const [hidden, setHidden] = useState<{ type: "bar"; seriesId: string }[]>([]);
  const statistics: DailyChangesStatistics = dashboardDailyChanges(sources, period);
  const locales = usePlotLocales();
  const { numbers } = locales;
  const resourceName = (resource: string) => translate(`dashboard.activity.resourceNames.${resource}`, {
    _: translate(`resources.${resource}.plural`, { _: resource }),
  });

  const body = () => {
    if (statistics.status !== "ready") return <PlotState status={statistics.status} />;
    const { days, series: verified, unavailable, total } = statistics;
    const stacked = verified.filter(line => !hidden.some(entry => entry.seriesId === line.resource));
    const maxValue = Math.max(1, ...days.map((_day, index) =>
      stacked.reduce((sum, line) => sum + (line.data[index] ?? 0), 0)));
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
        slotProps={{ legend: plotLegend }}
        xAxis={dayAxis(days, theme, locales, { scaleType: "band", height: 22, namedDays: NAMED_DAYS })}
        yAxis={countAxis(maxValue, translate("dashboard.changes.yAxis"), theme, numbers, VALUE_TICKS)}
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
    <ChartCard
      icon={<StackedBarChartIcon fontSize="small" color="primary" />}
      title={translate("dashboard.changes.title")}
      subheader={translate("dashboard.changes.scope", { days: period })}
      fill
    >
      {body()}
    </ChartCard>
  );
};

export default DailyChangesChart;
