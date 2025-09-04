import { useTheme } from '@mui/material/styles';
import { AllSeriesType, ChartContainerProps } from '@mui/x-charts';
import { ChartSeriesType } from '@mui/x-charts/internals';
import { useMemo } from 'react';
import { useListContext, useResourceDefinition } from 'react-admin';
import GradientChartContainer from '../../../MUI/GradientChartContainer';
import HistoryListBase from './HistoryListBase';

export interface HistoryChartProps extends ChartContainerProps{
  resource?: string
  total?: number
  filter?: any
}


const HistoryChartCore = (
  {
    total = 0,
    ...props
  }: HistoryChartProps
) => {
  const { name } = useResourceDefinition()
  const { data } = useListContext();

  const theme = useTheme();

  const monthlyStats = useMemo(()=>{
    if (!data || data.length === 0) return [];

    // Erstelle ein Map für schnelleren Zugriff nach Datum
    const dataMap = new Map<string, any>();
    data?.forEach(record => {
      
      const day = new Date(record?.historyDay).toISOString().split("T")[0]; // Nur yyyy-mm-dd
      dataMap.set(day, record);
    });

    const today = new Date();
    const result: any[] = [];

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
    const newDataSeries: any[] = []
    const deletedDataSeries: any[] = []
    const updatedDataSeries: any[] = []
    const dailyTotal: any[] = []
    
    const series = [
      { type: 'line', data: dailyTotal, label: name, area: true, showMark: true, color: theme.palette.primary.main || '', id: 'stats'},
      //{ type: 'line', data: newDataSeries, label:'new' ,},
      //{ type: 'line', data: deletedDataSeries, label:'deleted'},
      //{ type: 'line', data: updatedDataSeries, label:'updated'},
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
      scaleType: 'band',
      data: monthlyStats?.map(data => (data.id)) || [],
      id: 'x-axis-id',
      height: 45,
      position: 'none'
    }]
  ),[monthlyStats])

  
  return (
    <GradientChartContainer
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