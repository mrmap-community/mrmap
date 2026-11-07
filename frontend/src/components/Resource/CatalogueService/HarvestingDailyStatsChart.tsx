import { useMemo } from 'react';
import { useListContext, useTranslate } from 'react-admin';

import { useTheme } from '@mui/material/styles';
import { AllSeriesType, ChartsContainerProps } from '@mui/x-charts';
import { ChartSeriesType } from '@mui/x-charts/internals';

import GradientChartsContainer from '../../MUI/GradientChartsContainer';
import HistoryListBase from '../Generic/History/HistoryListBase';



export interface HistoryChartProps extends Omit<ChartsContainerProps, "filter">{
  resource?: string
  total?: number
  filter?: import("react-admin").FilterPayload
}


const HarvestingDailyStatsCore = (
  {
    filter: _filter, resource: _resource, ...props
  }: HistoryChartProps
) => {
  const { data } = useListContext();

  const theme = useTheme();
  const translate = useTranslate();

  const monthlyStats = useMemo(()=>{
    if (!data || data.length === 0) return [];

    // Erstelle ein Map für schnelleren Zugriff nach Datum
    const dataMap = new Map<string, import("react-admin").RaRecord>();
    data?.forEach(record => {
      const day = new Date(record?.day).toISOString().split("T")[0]; // Nur yyyy-mm-dd
      dataMap.set(day, record);
    });

    const today = new Date();
    const result: import("react-admin").RaRecord[] = [];
    let lastTotal = 0; // Zum Fortschreiben der Werte

    for (let i = 29; i >= 0; i--) {
      const date = new Date();
      date.setDate(today.getDate() - i);
      const dayStr = date.toISOString().split("T")[0];

      const existingStats = dataMap.get(dayStr);
      const stats = {
        id: dayStr,
        day: dayStr,
        new: existingStats?.new ?? 0,
        updated: existingStats?.updated ?? 0,
        existed: existingStats?.existed ?? 0,
        total: 0
      }

      if (existingStats) {
        stats.total = stats.new + stats.updated + stats.existed;
        lastTotal = stats.total; // Update last known total
      } else {
        stats.total = lastTotal; // Fortgeschriebener Wert
      }

      result.push(stats);
    }

    return result;
   
  },[data])

  const series = useMemo<Readonly<AllSeriesType<ChartSeriesType>>[]>(() => {
    const dailyTotal: number[] = []

    const series = [
      { type: 'line' as const, data: dailyTotal, label: translate('harvestingStats.records'), connectNulls: true, area: true, showMark: true, color: theme.palette.primary.main || '', id: 'stats'},
    ]

    monthlyStats?.forEach(data => {
      dailyTotal.push(data.total ?? 0)
    })

    return series
  }, [monthlyStats, theme, translate])


  const xAxis = useMemo(()=>(
    [{
      scaleType: 'band' as const,
      data: monthlyStats?.map(data => (data.id)) || [],
      id: 'x-axis-id',
      height: 45,
      yAxisId: 'y-axis-id',
      label: translate('harvestingStats.day'),
    }]
  ),[monthlyStats, translate])
  
  return (
    <GradientChartsContainer
      series={series}
      xAxis={xAxis}
      yAxis={[{
          id: 'y-axis-id',
          scaleType: 'linear',
          position: 'left',
          label: translate('harvestingStats.records')
        }]}
      {...props}
    />
  )
}


const HarvestingDailyStatsChart = (  {
    resource,
    total = 0,
    filter,
    ...props
  }: HistoryChartProps) => {

  return (
    <HistoryListBase
      resource={resource}
      filter={filter}
    >
      <HarvestingDailyStatsCore
        total={total}
        {...props}
      />
    </HistoryListBase>
  )

};


export default HarvestingDailyStatsChart;