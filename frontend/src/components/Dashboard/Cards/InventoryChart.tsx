import { useId, useState } from "react";
import { useLocaleState, useTranslate } from "react-admin";

import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import StorageIcon from "@mui/icons-material/Storage";
import { Alert, Box, IconButton, Popover, Stack, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { LineChart } from "@mui/x-charts/LineChart";

import SimpleCard from "../../MUI/SimpleCard";
import { dashboardResourceColor } from "../dashboardColors";
import {
  dashboardInventory,
  type InventorySource,
  type InventoryStatistics,
} from "../dashboardInventory";

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
  const [locale] = useLocaleState();
  const id = useId();
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const numbers = new Intl.NumberFormat(locale);
  const dates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const counts = new Map(statistics.status === "ready"
    ? statistics.series.map(line => [line.resource, line.count] as const) : []);
  const days = statistics.status === "ready" ? statistics.days : undefined;
  return <>
    <Tooltip title={translate("dashboard.inventory.coverage")}>
      <IconButton size="small" aria-label={translate("dashboard.inventory.coverage")}
        aria-haspopup="dialog" aria-expanded={Boolean(anchor)} aria-controls={anchor ? id : undefined}
        onClick={event => setAnchor(event.currentTarget)}>
        <InfoOutlinedIcon fontSize="small" />
      </IconButton>
    </Tooltip>
    <Popover id={id} open={Boolean(anchor)} anchorEl={anchor} onClose={() => setAnchor(null)}
      anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}
      slotProps={{ paper: { role: "dialog", "aria-label": translate("dashboard.inventory.coverage"), sx: { p: 2, width: 360, maxWidth: "calc(100% - 32px)" } } }}>
      <Typography variant="subtitle2" component="h3">{translate("dashboard.inventory.coverage")}</Typography>
      <Typography variant="body2" sx={{ my: 1 }}>{translate("dashboard.inventory.scope")}</Typography>
      <Box component="ul" sx={{ pl: 2, my: 1 }}>
        {(statistics.status === "ready"
          ? [...statistics.series.map(line => line.resource), ...statistics.unavailable.map(gap => gap.resource)]
          : []
        ).map(resource => <Typography component="li" variant="body2" key={resource}>
          {resourceName(resource)}:{" "}
          {counts.has(resource)
            ? translate("dashboard.inventory.verified", { count: numbers.format(counts.get(resource) ?? 0) })
            : translate("dashboard.inventory.unverified")}
        </Typography>)}
      </Box>
      {days && <Typography variant="body2" color="text.secondary">
        {translate("dashboard.activity.window", {
          from: dates.format(new Date(`${days[0]}T00:00:00Z`)),
          to: dates.format(new Date(`${days.at(-1) ?? ""}T00:00:00Z`)),
          days: days.length,
        })}
      </Typography>}
    </Popover>
  </>;
};

const InventoryPlot = ({ statistics, resourceName }: {
  statistics: InventoryStatistics;
  resourceName: (resource: string) => string;
}) => {
  const translate = useTranslate();
  const [locale] = useLocaleState();
  const theme = useTheme();
  const [hidden, setHidden] = useState<{ type: "line"; seriesId: string }[]>([]);
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
  const maxValue = Math.max(1, ...verified.flatMap(line => [...line.data, line.count]));
  const step = valueStep(maxValue);
  const ticks = Array.from({ length: Math.ceil(maxValue / step) + 1 }, (_, index) => index * step);
  const series = verified.map(line => ({
    id: line.resource,
    label: resourceName(line.resource),
    data: line.data,
    curve: "linear" as const,
    area: true,
    showMark: false,
    color: dashboardResourceColor(theme, line.resource),
    valueFormatter: (value: number | null) => numbers.format(value ?? 0),
  }));
  return <Box>
    {hidden.length === series.length && series.length > 0
      && <Typography variant="caption" role="status">{translate("dashboard.activity.noSeries")}</Typography>}
    <LineChart
      aria-label={translate("dashboard.inventory.title")}
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
        label: translate("dashboard.inventory.yAxis"),
        labelStyle: { fontSize: 11, fontWeight: 600, fill: theme.palette.text.primary },
        tickLabelStyle: { fontSize: 11, fill: theme.palette.text.secondary },
        valueFormatter: (value: number) => numbers.format(value),
      }]}
      margin={{ left: 0, right: 26, top: 8, bottom: 0 }}
      grid={{ horizontal: true }}
      sx={{
        "& .MuiChartsGrid-line": { stroke: theme.palette.divider },
        "& .MuiLineChart-area": { fillOpacity: 0.12 },
      }}
      skipAnimation
    />
    {unavailable.length > 0 && <Typography variant="caption" color="warning.main" role="status">
      {translate("dashboard.inventory.unavailable", { resources: unavailable.map(gap => resourceName(gap.resource)).join(", ") })}
    </Typography>}
    {verified.every(line => line.data.every(value => value === 0) && line.count === 0)
      && <Typography variant="caption" role="status">{translate("dashboard.inventory.empty")}</Typography>}
  </Box>;
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
    <SimpleCard
      title={<Stack direction="row" useFlexGap sx={{ alignItems: "center", columnGap: 0.25, minWidth: 0 }}>
        <StorageIcon fontSize="small" color="primary" />
        <Typography component="h2" variant="subtitle2" sx={{ minWidth: 0 }} noWrap>
          {translate("dashboard.inventory.title")}
        </Typography>
        <InventoryCoverage statistics={statistics} resourceName={resourceName} />
      </Stack>}
      headerProps={{ sx: { alignItems: "center", minHeight: 40, px: 1.5, py: 0.25 } }}
      cardProps={{ variant: "outlined", sx: { minWidth: 0, boxShadow: "none", borderRadius: 2 } }}
      contentProps={{ sx: { px: 0.5, pt: 0, pb: 0.5, "&:last-child": { pb: 0.5 } } }}
      divider={false}
    >
      <InventoryPlot statistics={statistics} resourceName={resourceName} />
    </SimpleCard>
  );
};

export default InventoryChart;
