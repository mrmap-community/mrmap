import type { ActivityStatus } from "../dashboardActivity";
import type { Theme } from "@mui/material/styles";
import type { VisibilityIdentifierWithType } from "@mui/x-charts/plugins";

import type { ReactNode } from "react";
import { useId, useState } from "react";
import { useLocaleState, useTranslate } from "react-admin";

import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { Alert, Box, IconButton, Popover, Stack, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { LineChart } from "@mui/x-charts/LineChart";

import SimpleCard from "../../MUI/SimpleCard";
import { dashboardResourceColor } from "../dashboardColors";

/** the days of a window a plot names on its axis, so a 30 day window names ten */
const NAMED_DAYS = 10;

/** the height of a time series plot; its card stays within the chart row of the mockup */
const PLOT_HEIGHT = 168;

/** the four answers which are not an answer yet, in the wording of the history cards */
export const STATE_MESSAGES = {
  loading: "historyChart.asking",
  error: "historyChart.error",
  partial: "historyChart.partial",
  unsupported: "historyChart.noStatistics",
} as const;

/** how loud each of those four answers is */
const STATE_SEVERITY = {
  loading: "info", error: "error", partial: "warning", unsupported: "info",
} as const;

/**
 * The answer of a plot which could not draw anything.
 *
 * No card of the screen keeps an empty frame standing for a read which did not
 * answer, and the four states stay apart: what is still being asked, what
 * failed, what answered incompletely and what the deployment cannot answer at
 * all are four different things for the administrator reading the screen.
 */
export const PlotState = ({ status }: { status: ActivityStatus }) => {
  const translate = useTranslate();
  return <Alert severity={STATE_SEVERITY[status]} role="status" sx={{ my: 1 }}>
    {translate(STATE_MESSAGES[status])}
  </Alert>;
};

/** the numbers and the days of a plot, in the locale of the user */
export const usePlotLocales = () => {
  const [locale] = useLocaleState();
  const numbers = new Intl.NumberFormat(locale);
  const dates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const shortDates = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" });
  return {
    numbers,
    formatDay: (day: string) => dates.format(new Date(`${day}T00:00:00Z`)),
    formatShortDay: (day: string) => shortDates.format(new Date(`${day}T00:00:00Z`)),
  };
};

/**
 * The whole numbers the value axis of a plot counts in.
 *
 * A count never counts fractions and an axis of this height answers only as many
 * labels as an administrator can read, so the step is the smallest of the series
 * 1, 2, 5 and 10 times a power of ten which keeps the labels that few.
 */
const valueStep = (max: number, maxTicks: number) => {
  const target = Math.max(1, max);
  const power = 10 ** Math.floor(Math.log10(target / 4));
  return [1, 2, 5, 10].map(multiplier => multiplier * power)
    .find(step => step >= 1 && Math.ceil(target / step) <= maxTicks) ?? Math.max(1, 10 * power);
};

const axisLabelStyle = (theme: Theme, isTitle: boolean) => ({
  fontSize: 11,
  fill: isTitle ? theme.palette.text.primary : theme.palette.text.secondary,
  ...(isTitle ? { fontWeight: 600 } : {}),
});

/** an answer of a plot exists only where its condition answers it, never as `false` */
export const when = (asked: boolean, answer: string) => (asked ? answer : undefined);

/** the legend of a plot: compact, centered under its series, and clickable */
export const plotLegend = {
  direction: "horizontal",
  toggleVisibilityOnClick: true,
  sx: { justifyContent: "center", columnGap: 2, rowGap: 0.25, fontSize: "0.75rem", minHeight: 24 },
} as const;

/**
 * The day axis of a plot.
 *
 * The days of the window are the categories and a bounded number of them is
 * named, so a 90 day window stays readable; the tooltip answers the whole date,
 * because over which days a card drew its answer has to be readable exactly and
 * never guessed from a short label.
 */
export const dayAxis = (
  days: string[],
  theme: Theme,
  locales: ReturnType<typeof usePlotLocales>,
  options: { scaleType?: "point" | "band"; height?: number; namedDays?: number } = {},
) => {
  const { scaleType = "point", height = 24, namedDays = NAMED_DAYS } = options;
  const step = Math.max(1, Math.ceil((days.length - 1) / namedDays));
  return [{
    scaleType,
    data: days,
    height,
    valueFormatter: (day: string, context: { location: string }) =>
      context.location === "tick" ? locales.formatShortDay(day) : locales.formatDay(day),
    tickInterval: (_day: string, index: number) => index % step === 0,
    tickLabelStyle: axisLabelStyle(theme, false),
  }];
};

/**
 * The value axis of a plot: whole numbers from zero, under a name which says
 * what is counted, so no axis of the screen reads as a count of something else.
 */
export const countAxis = (
  max: number,
  label: string,
  theme: Theme,
  numbers: Intl.NumberFormat,
  maxTicks: number = 5,
) => {
  const step = valueStep(max, maxTicks);
  const ticks = Array.from({ length: Math.ceil(max / step) + 1 }, (_, index) => index * step);
  return [{
    min: 0, max: ticks.at(-1), tickNumber: ticks.length, tickMinStep: 1,
    domainLimit: "strict" as const, width: "auto" as const,
    label,
    labelStyle: axisLabelStyle(theme, true),
    tickLabelStyle: axisLabelStyle(theme, false),
    valueFormatter: (value: number) => numbers.format(value),
  }];
};

/**
 * The statistical scope of a card, asked for and never standing in it.
 *
 * Every chart of the screen counts something an administrator can confuse with
 * something else — events with objects, a stock with the sum of events — so each
 * card carries the answer to "what exactly is this" behind one icon, together
 * with the coverage of the series it drew.
 */
export const Coverage = ({ label, children }: { label: string; children: ReactNode }) => {
  const id = useId();
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  return <>
    <Tooltip title={label}>
      <IconButton size="small" aria-label={label}
        aria-haspopup="dialog" aria-expanded={Boolean(anchor)} aria-controls={anchor ? id : undefined}
        onClick={event => setAnchor(event.currentTarget)}>
        <InfoOutlinedIcon fontSize="small" />
      </IconButton>
    </Tooltip>
    <Popover id={id} open={Boolean(anchor)} anchorEl={anchor} onClose={() => setAnchor(null)}
      anchorOrigin={{ vertical: "bottom", horizontal: "right" }} transformOrigin={{ vertical: "top", horizontal: "right" }}
      slotProps={{ paper: { role: "dialog", "aria-label": label, sx: { p: 2, width: 360, maxWidth: "calc(100% - 32px)" } } }}>
      <Typography variant="subtitle2" component="h3">{label}</Typography>
      {children}
    </Popover>
  </>;
};

/** one line of a time series plot, with the peak which is drawn but never a day */
export interface PlotLine {
  resource: string;
  data: number[];
  /** a value of the resource outside the days, which the axis still has to fit */
  peak?: number;
}

/**
 * The line plot two cards of the screen share.
 *
 * The activity chart and the inventory chart draw the same shape — one area line
 * per verified resource over the days of the window the header chose, with one
 * clickable legend and axes which count in whole numbers — and differ only in
 * what their lines are made of and in what they say when nothing is left to
 * draw. Both answers are handed in by the card, so the two of them cannot drift
 * apart in the one thing an administrator compares between them.
 */
export const LinePlot = ({ title, yAxisLabel, days, lines, resourceName, marks = false, verticalGrid = false, unavailable, empty }: {
  title: string;
  yAxisLabel: string;
  days: string[];
  lines: PlotLine[];
  resourceName: (resource: string) => string;
  /** marks make a single day of an event series readable, a stock does not need them */
  marks?: boolean;
  verticalGrid?: boolean;
  unavailable?: string;
  empty?: string;
}) => {
  const translate = useTranslate();
  const theme = useTheme();
  const [hidden, setHidden] = useState<VisibilityIdentifierWithType<"line">[]>([]);
  const locales = usePlotLocales();
  const { numbers } = locales;
  const maxValue = Math.max(1, ...lines.flatMap(line => [...line.data, line.peak ?? 0]));
  const series = lines.map(line => ({
    id: line.resource,
    label: resourceName(line.resource),
    data: line.data,
    curve: "linear" as const,
    area: true,
    showMark: marks,
    ...(marks && { shape: "circle" as const }),
    color: dashboardResourceColor(theme, line.resource),
    valueFormatter: (value: number | null) => numbers.format(value ?? 0),
  }));
  return <Box>
    {hidden.length === series.length && series.length > 0
      && <Typography variant="caption" role="status">{translate("dashboard.activity.noSeries")}</Typography>}
    <LineChart
      aria-label={title}
      height={PLOT_HEIGHT}
      series={series}
      hiddenItems={hidden}
      onHiddenItemsChange={setHidden}
      slotProps={{ legend: plotLegend }}
      xAxis={dayAxis(days, theme, locales)}
      yAxis={countAxis(maxValue, yAxisLabel, theme, numbers)}
      margin={{ left: 0, right: 26, top: 8, bottom: 0 }}
      grid={{ horizontal: true, vertical: verticalGrid }}
      sx={{
        "& .MuiChartsGrid-line": { stroke: theme.palette.divider },
        "& .MuiLineChart-area": { fillOpacity: 0.12 },
        ...(marks && { "& .MuiLineChart-mark": { stroke: theme.palette.background.paper, strokeWidth: 1 } }),
      }}
      skipAnimation
    />
    {unavailable && <Typography variant="caption" color="warning.main" role="status">{unavailable}</Typography>}
    {empty && <Typography variant="caption" role="status">{empty}</Typography>}
  </Box>;
};

/**
 * The frame every chart of the dashboard answers in.
 *
 * One icon, one title, the scope behind it and the answer of the plot: the cards
 * of the screen differ in what they draw and never in the frame around it, so
 * the row of the mockup cannot drift into cards of different heights, paddings or
 * header alignment. A card of a row which shares its height with a neighbour says
 * so with `fill`, and one which answers a window below its title says so with a
 * `subheader`.
 */
export const ChartCard = ({ icon, title, action, subheader, fill = false, contentPaddingX = 0.5, children }: {
  icon: ReactNode;
  title: string;
  /** the scope of the card, which answers beside its title */
  action?: ReactNode;
  subheader?: string;
  fill?: boolean;
  contentPaddingX?: number;
  children: ReactNode;
}) => (
  <SimpleCard
    title={<Stack direction="row" useFlexGap sx={{ alignItems: "center", columnGap: 0.25, minWidth: 0 }}>
      {icon}
      <Typography component="h2" variant="subtitle2" sx={{ minWidth: 0 }} noWrap>{title}</Typography>
      {action}
    </Stack>}
    {...(subheader && {
      subheader: <Typography variant="caption" color="text.secondary">{subheader}</Typography>,
    })}
    headerProps={{ sx: { alignItems: subheader ? "flex-start" : "center", minHeight: 40, px: 1.5, py: 0.25 } }}
    cardProps={{
      variant: "outlined",
      sx: { minWidth: 0, boxShadow: "none", borderRadius: 2, ...(fill && { height: "100%" }) },
    }}
    contentProps={{ sx: { px: contentPaddingX, pt: 0, pb: 0.5, "&:last-child": { pb: 0.5 } } }}
    divider={false}
  >
    {children}
  </SimpleCard>
);
