import { useMemo } from 'react';
import { useListContext, useResourceDefinition } from 'react-admin';

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


const HistoryChartCore = (
  {
    total = 0,
    filter: _filter, resource: _resource, ...props
  }: HistoryChartProps
) => {
  const { name } = useResourceDefinition()
  const { data } = useListContext();

  const theme = useTheme();

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

    for (let i = 29; i >= 0; i--) {
      const date = new Date();
      date.setDate(today.getDate() - i);
      const dayStr = date.toISOString().split("T")[0];

      const existing = dataMap.get(dayStr);
      result.push({
        id: dayStr,
        day: dayStr,
        new: existing?.new ?? 0,
        deleted: existing?.deleted ?? 0,
        updated: existing?.updated ?? 0,
        existed: existing?.existed ?? 0,
        total: 0, // wird im nächsten Schritt berechnet
      });
    }
    // Total-Werte berechnen (beginnend mit bekanntem Total am letzten Tag)
    result[result.length - 1].total = total;

    for (let i = result.length - 2; i >= 0; i--) {
      const next = result[i + 1];
      result[i].total = next.total - next.new + next.deleted;
    }

    return result;
   
  },[data, total])

  const series = useMemo<Readonly<AllSeriesType<ChartSeriesType>>[]>(() => {
    const newDataSeries: number[] = []
    const deletedDataSeries: number[] = []
    const updatedDataSeries: number[] = []
    const dailyTotal: number[] = []
    
    const series = [
      { type: 'line' as const, data: dailyTotal, label: name, area: true, showMark: true, color: theme.palette.primary.main || '', id: 'stats'},
      //{ type: 'line' as const, data: newDataSeries, label:'new' ,},
      //{ type: 'line' as const, data: deletedDataSeries, label:'deleted'},
      //{ type: 'line' as const, data: updatedDataSeries, label:'updated'},
    ]
  
    monthlyStats?.forEach(data => {
      dailyTotal.push(data.total ?? 0)
      newDataSeries.push(data.new ?? 0)
      deletedDataSeries.push(data.deleted ?? 0)
      updatedDataSeries.push(data.updated ?? 0)
    })

    return series
  }, [monthlyStats])


  const xAxis = useMemo(()=>(
    [{
      scaleType: 'band' as const,
      data: monthlyStats?.map(data => (data.id)) || [],
      id: 'x-axis-id',
      height: 45,
      position: 'none' as const
    }]
  ),[monthlyStats])

  
  return (
    <GradientChartsContainer
      series={series}
      xAxis={xAxis}
      {...props}
    />
  )
}


const HistoryChart = (  {
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
      <HistoryChartCore
        total={total}
        {...props}
      />
    </HistoryListBase>
  )

};


export default HistoryChart;