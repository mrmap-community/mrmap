import { useMemo } from 'react';
import { useListContext, useResourceDefinition, useTranslate } from 'react-admin';

import { Stack, Typography } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { AllSeriesType, ChartsContainerProps } from '@mui/x-charts';
import { ChartSeriesType } from '@mui/x-charts/internals';

import GradientChartsContainer from '../../../MUI/GradientChartsContainer';
import HistoryListBase from './HistoryListBase';

export interface HistoryChartProps extends Omit<ChartsContainerProps, "filter">{
  resource?: string
  total?: number
  filter?: import("react-admin").FilterPayload
}

/** the days of the past the chart of a resource counts the changes of */
export const CHANGE_DAYS = 30;

/** the amount of days of the window the axis of the chart names */
const NAMED_DAYS = 5;

/**
 * The day a statistic of the api belongs to, as the chart asks it back.
 *
 * The api answers the day of the resource as a plain day of the month, and a day
 * of the month is never moved into another day by the timezone of the viewer, so
 * an answered day is taken as it is and only an instant is read as a day.
 */
const dayOf = (day: unknown) => {
  if (typeof day === 'string') return day.slice(0, 10);
  const date = new Date(day as string | number);
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
};

/**
 * The day of the window named for the viewer.
 *
 * A day of the month is read as the day the resource counts it and never moved
 * into another day by the timezone of the viewer, so it is named from the parts
 * of the day and not from an instant of it.
 *
 * @param day the day to name, as yyyy-mm-dd
 * @returns the day named in the language of the viewer
 */
const dayLabel = (day: string) => new Intl.DateTimeFormat(undefined, {
  day: "2-digit",
  month: "short",
}).format(new Date(`${day}T00:00:00`));

/**
 * The days of the window the axis of the chart names, so that the chart names its
 * dates without asking for the width it is drawn in.
 *
 * The window of a card is drawn in the width of a card, so the axis cannot name
 * every day of it and must name the last day of the window and the days which lie
 * a step before it.
 *
 * @param days the days of the window, oldest first, as yyyy-mm-dd
 * @returns the days the axis names
 */
export const namedDays = (days: string[]): Set<string> => {
  const named = new Set<string>();
  if (!days.length) return named;
  const step = Math.max(1, Math.floor((days.length - 1) / (NAMED_DAYS - 1)));
  for (let index = days.length - 1; index >= 0; index -= step) {
    named.add(days[index]);
  }
  return named;
};

/** the given amount of days before today, oldest first, as yyyy-mm-dd */
export const lastDays = (days: number): string[] => {
  const today = new Date();
  return Array.from({ length: days }, (_unused, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() - (days - 1 - index));
    return dayOf(date);
  });
};

/** the changes of one day of the window of the chart */
export interface DailyChange {
  /** the day the change belongs to, as yyyy-mm-dd */
  id: string
  /** what was added to the inventory of the resource that day */
  new: number
  /** what was updated in the inventory of the resource that day */
  updated: number
  /** what was taken out of the inventory of the resource that day */
  deleted: number
  /** the inventory the resource counted that day */
  total: number
}

/**
 * The changes of the given days, oldest first, and the inventory which was
 * answered for the day after them.
 *
 * The api answers only the days which did have a change, so a day without an
 * answer is a day without any change and never a hole. The inventory of the
 * oldest day is stepped back from the inventory of today, because the api
 * answers the changes per day and not the inventory per day.
 *
 * @param data the statistics the api answered for the resource
 * @param total the inventory the resource counts today
 * @param days the days of the window, oldest first, as yyyy-mm-dd
 * @returns the changes of every day of the window, oldest first
 */
export const changesOfDays = (
  data: import("react-admin").RaRecord[] | undefined,
  total: number,
  days: string[]
): DailyChange[] => {
  const byDay = new Map<string, import("react-admin").RaRecord>();
  data?.forEach(record => byDay.set(dayOf(record?.day), record));

  const changes = days.map(day => {
    const answered = byDay.get(day);
    return {
      id: day,
      new: answered?.new ?? 0,
      updated: answered?.updated ?? 0,
      deleted: answered?.deleted ?? 0,
      total: 0,
    };
  });

  // the last day of the window carries the inventory the resource counts today
  let inventory = total;
  for (let index = changes.length - 1; index >= 0; index--) {
    changes[index].total = inventory;
    inventory = inventory - changes[index].new + changes[index].deleted;
  }

  return changes;
}

/**
 * The changes of a resource, drawn as stacked bars of what changed and as a line
 * of the inventory which was counted after them.
 *
 * What the card says when the statistics are not answered yet, or not answered
 * at all, or not answered by the resource, is told by HistoryChartState - each of
 * them is another answer and only the answered changes are drawn.
 */
export const HistoryChartCore = (
  {
    changes,
    ...props
  }: {
    /** the changes of the days of the window, oldest first */
    changes: DailyChange[]
  } & Omit<HistoryChartProps, "resource" | "total" | "filter">
) => {
  const { name } = useResourceDefinition()
  const translate = useTranslate();

  const theme = useTheme();

  const series = useMemo<Readonly<AllSeriesType<ChartSeriesType>>[]>(() => {
    const totals: number[] = []
    const added: number[] = []
    const changed: number[] = []
    const removed: number[] = []

    changes.forEach(day => {
      totals.push(day.total)
      added.push(day.new)
      changed.push(day.updated)
      removed.push(day.deleted)
    })

    // the additions, the updates and the deletions are stacked, so a day reads as
    // the amount it changed and the line above them reads as the inventory the
    // card counts - the chart never draws a change as a part of the inventory
    const series = [
      { type: 'line' as const, data: totals, label: translate('historyChart.total', { unit: name }), area: true, showMark: true, color: theme.palette.primary.main || '', id: 'stats'},
      { type: 'bar' as const, data: added, label: translate('historyChart.new'), stack: 'changes', color: theme.palette.success.main },
      { type: 'bar' as const, data: changed, label: translate('historyChart.updated'), stack: 'changes', color: theme.palette.info.main },
      { type: 'bar' as const, data: removed, label: translate('historyChart.deleted'), stack: 'changes', color: theme.palette.error.main },
    ]

    return series
  }, [changes, name, theme, translate])

  const xAxis = useMemo(()=>{
    const named = namedDays(changes.map(day => day.id));
    return [{
      scaleType: 'band' as const,
      data: changes.map(day => day.id),
      id: 'x-axis-id',
      height: 45,
      // the window of a card does not fit every day of it into its width, so the
      // axis names the days it can and spreads them over the window
      labelFormatter: (day: string) => (named.has(day) ? dayLabel(day) : ''),
      // the tooltip of the chart names the day of every value it shows, so the day
      // of a bar is read even when the axis has no room to name it
      valueFormatter: (day: string) => dayLabel(day),
    }]
  },[changes])

  return (
    <Stack spacing={0}>
      <GradientChartsContainer
        series={series}
        xAxis={xAxis}
        {...props}
      />
      {/* the axis names no day, so the caption says over what time the card counts,
          in which unit and of which resource */}
      <Typography variant="caption" color="text.secondary">
        {translate("historyChart.caption", { days: changes.length, unit: name })}
      </Typography>
    </Stack>
  )
}


/**
 * What the card says about the statistics of a resource before they are drawn.
 *
 * The states are told apart because each of them is another answer: the resource
 * answers no statistics at all, the statistics are asked and not answered yet,
 * the request failed or the resource answers its changes. Only the last of them
 * is drawn as a chart and only a resource which answers no change at all is drawn
 * as an inventory which does not move.
 */
const HistoryChartState = (
  {
    total,
    ...props
  }: {
    total: number
  } & Omit<HistoryChartProps, "resource" | "filter">
) => {
  const { data, isPending, error } = useListContext();
  const translate = useTranslate();

  if (isPending)
    return <Typography variant="body2" color="text.secondary">{translate('historyChart.asking')}</Typography>

  if (error)
    return <Typography variant="body2" color="text.error">{translate('historyChart.error')}</Typography>

  return <HistoryChartCore
    changes={changesOfDays(data, total, lastDays(CHANGE_DAYS))}
    {...props}
  />
}


/**
 * The changes of a resource in the days of the past the card of that resource
 * counts the changes of.
 */
const HistoryChart = (  {
    resource,
    total = 0,
    filter,
    ...props
  }: HistoryChartProps) => {
  const translate = useTranslate();

  return (
    <HistoryListBase
      resource={resource}
      filter={filter}
      // a resource which answers no statistics at all is not a resource without
      // changes, so it says so instead of leaving the card without a chart
      fallback={<Typography variant="body2" color="text.secondary">{translate('historyChart.noStatistics')}</Typography>}
    >
      <HistoryChartState
        total={total}
        {...props}
      />
    </HistoryListBase>
  )

};


export default HistoryChart;