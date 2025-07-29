import { useTheme } from '@mui/material/styles';
import { AllSeriesType, ChartContainerProps } from '@mui/x-charts';
import { ChartSeriesType } from '@mui/x-charts/internals';
import { useMemo } from 'react';
import { useListContext } from 'react-admin';
import GradientChartContainer from '../../MUI/GradientChartContainer';
import HistoryListBase from '../Generic/History/HistoryListBase';



export interface HistoryChartProps extends ChartContainerProps{
  resource?: string
  total?: number
  filter?: any
}


const HarvestingDailyStatsCore = (
  {
    ...props
  }: HistoryChartProps
) => {
  const { data } = useListContext();

  const theme = useTheme();

  const monthlyStats = useMemo(()=>{
    if (!data || data.length === 0) return [];

    // Erstelle ein Map für schnelleren Zugriff nach Datum
    const dataMap = new Map<string, any>();
    data?.forEach(record => {
      const day = new Date(record?.day).toISOString().split("T")[0]; // Nur yyyy-mm-dd
      dataMap.set(day, record);
    });

    const today = new Date();
    const result: any[] = [];
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
    const newDataSeries: any[] = []
    const deletedDataSeries: any[] = []
    const updatedDataSeries: any[] = []
    const existedDataSeries: any[] = []

    const dailyTotal: any[] = []
    
    const series = [
      { type: 'line', data: dailyTotal, label: 'Records', connectNulls: true, area: true, showMark: true, color: theme.palette.primary.main || '', id: 'stats'},
      //{ type: 'line', data: newDataSeries, label:'new' ,},
      //{ type: 'line', data: deletedDataSeries, label:'deleted'},
      //{ type: 'line', data: updatedDataSeries, label:'updated'},
      //{ type: 'line', data: existedDataSeries, label:'existed'},
    ]
  
    monthlyStats?.forEach(data => {
      dailyTotal.push(data.total ?? 0)
      newDataSeries.push(data.new ?? 0)
      deletedDataSeries.push(data.deleted ?? 0)
      updatedDataSeries.push(data.updated ?? 0)
      existedDataSeries.push(data.existed ?? 0)
    })

    return series
  }, [monthlyStats])


  const xAxis = useMemo(()=>(
    [{
      scaleType: 'band',
      data: monthlyStats?.map(data => (data.id)) || [],
      id: 'x-axis-id',
      height: 45,
      yAxisId: 'y-axis-id',
      label: 'Day',
    }]
  ),[monthlyStats])
  
  return (
    <GradientChartContainer
      series={series}
      xAxis={xAxis}
      yAxis={[{
          id: 'y-axis-id',
          scaleType: 'linear',
          position: 'left',
          label: 'Records'
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