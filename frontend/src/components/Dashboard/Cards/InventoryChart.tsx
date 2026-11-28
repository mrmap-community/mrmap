import { useTranslate } from "react-admin";

import StorageIcon from "@mui/icons-material/Storage";
import { Box, Typography } from "@mui/material";

import {
  dashboardInventory,
  type InventorySource,
  type InventoryStatistics,
} from "../dashboardInventory";
import { ChartCard, Coverage, LinePlot, PlotState, usePlotLocales, when } from "./ChartParts";

/**
 * The statistical scope of the inventory, asked for and never standing in the card.
 *
 * An inventory is a stock, which is what an administrator must be able to tell
 * from the events of the activity chart beside it; the popover says that, names
 * the resources whose stock is verified with the count they answer today, and
 * names the ones which cannot answer.
 */
const InventoryCoverage = ({ statistics, resourceName }: {
  statistics: InventoryStatistics;
  resourceName: (resource: string) => string;
}) => {
  const translate = useTranslate();
  const { numbers, formatDay } = usePlotLocales();
  const counted = new Map(statistics.status === "ready"
    ? statistics.series.map(line => [line.resource, line.count] as const) : []);
  const days = statistics.status === "ready" ? statistics.days : undefined;
  const asked = statistics.status === "ready"
    ? [...statistics.series.map(line => line.resource), ...statistics.unavailable.map(gap => gap.resource)]
    : [];
  return <Coverage label={translate("dashboard.inventory.coverage")}>
    <Typography variant="body2" sx={{ my: 1 }}>{translate("dashboard.inventory.scope")}</Typography>
    <Box component="ul" sx={{ pl: 2, my: 1 }}>
      {asked.map(resource => <Typography component="li" variant="body2" key={resource}>
        {resourceName(resource)}:{" "}
        {counted.has(resource)
          ? translate("dashboard.inventory.verified", { count: numbers.format(counted.get(resource) ?? 0) })
          : translate("dashboard.inventory.unverified")}
      </Typography>)}
    </Box>
    {days && <Typography variant="body2" color="text.secondary">
      {translate("dashboard.activity.window", {
        from: formatDay(days[0]),
        to: formatDay(days.at(-1) ?? ""),
        days: days.length,
      })}
    </Typography>}
  </Coverage>;
};

const InventoryPlot = ({ statistics, resourceName }: {
  statistics: InventoryStatistics;
  resourceName: (resource: string) => string;
}) => {
  const translate = useTranslate();
  if (statistics.status !== "ready") return <PlotState status={statistics.status} />;
  const { days, series: verified, unavailable } = statistics;
  return <LinePlot
    title={translate("dashboard.inventory.title")}
    yAxisLabel={translate("dashboard.inventory.yAxis")}
    days={days}
    lines={verified.map(line => ({ resource: line.resource, data: line.data, peak: line.count }))}
    resourceName={resourceName}
    unavailable={when(unavailable.length > 0, translate("dashboard.inventory.unavailable", {
      resources: unavailable.map(gap => resourceName(gap.resource)).join(", "),
    }))}
    empty={when(verified.every(line => line.data.every(value => value === 0) && line.count === 0),
      translate("dashboard.inventory.empty"))}
  />;
};

/**
 * The inventory of the deployment over the selected period.
 *
 * The right half of the chart row of the mockup and the counterpart of the
 * activity chart: this one answers the stock a resource counted on each day of
 * the window, the other one answers the audit events of it. A line is drawn
 * from the verified stock of its own resource alone (#1817) and never from the
 * event totals — where the stock of a resource cannot be proved, the card names
 * it instead of drawing a line, because an invented stock is the one answer this
 * card must never give.
 */
const InventoryChart = ({ sources }: {
  /** the verified sources of the dashboard, which the other cards share */
  sources: InventorySource[];
}) => {
  const translate = useTranslate();
  const statistics = dashboardInventory(sources);
  const resourceName = (resource: string) => translate(`dashboard.activity.resourceNames.${resource}`, {
    _: translate(`resources.${resource}.plural`, { _: resource }),
  });
  return (
    <ChartCard
      icon={<StorageIcon fontSize="small" color="primary" />}
      title={translate("dashboard.inventory.title")}
      action={<InventoryCoverage statistics={statistics} resourceName={resourceName} />}
    >
      <InventoryPlot statistics={statistics} resourceName={resourceName} />
    </ChartCard>
  );
};

export default InventoryChart;
