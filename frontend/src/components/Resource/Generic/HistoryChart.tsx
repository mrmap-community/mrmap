import { alpha, useTheme } from '@mui/material/styles';
import { AllSeriesType, AreaPlot, ChartContainer, ChartContainerProps, ChartsLegend, ChartsTooltip, LineHighlightPlot, LinePlot } from '@mui/x-charts';
import { ChartSeriesType } from '@mui/x-charts/internals';
import { useMemo } from 'react';
import { useGetList, useListContext, useResourceDefinition } from 'react-admin';
import { useHttpClientContext } from '../../../context/HttpClientContext';

export interface HistoryChartProps extends ChartContainerProps{
  resource?: string
}


const Chart = (
  {
    resource,
    ...props
  }: HistoryChartProps
) => {
  const { name } = useResourceDefinition({resource: resource})

  const { total } = useListContext();

  const { data } = useGetList(`Statistical${name}`, {sort: {field: "id", order: "DESC"}})

  const theme = useTheme();

  const monthlyStats = useMemo(()=>{
    if (!data || data.length === 0) return [];

    // Erstelle ein Map für schnelleren Zugriff nach Datum
    const dataMap = new Map<string, any>();

    data.forEach(record => {
      const day = new Date(record.day).toISOString().split("T")[0]; // Nur yyyy-mm-dd
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
    <ChartContainer
        series={series}
        xAxis={xAxis}
        yAxis={[{
          width: 30,
          position: 'none'
        }]}
        //yAxis={[{ label: 'rainfall (mm)', width: 60 }]}
        //colors={mangoFusionPalette}
        //height={300}
        margin={{ top: 5, bottom: 0, right: 0, left: 0 }}
        sx={{
          '& .MuiAreaElement-series-stats': { fill: "url('#myGradient1')", strokeWidth: 2, opacity: 0.8 }
        }}
        {...props}
      >
        <defs>
          <linearGradient id="myGradient1" gradientTransform="rotate(90)">
            <stop offset="10%" stopColor={alpha(theme.palette.primary.main, 0.4)} />
            <stop offset="90%" stopColor={alpha(theme.palette.background.default, 0.4)} />
          </linearGradient>
        </defs>
        <AreaPlot />
        <LinePlot />
        <LineHighlightPlot />
        <ChartsLegend direction="horizontal" />
        <ChartsTooltip />
    </ChartContainer >
  )

}


const HistoryChart = (
  {
    resource,
    ...props
  }: HistoryChartProps
) => {
  const { name } = useResourceDefinition({resource: resource})
  
  const { api } = useHttpClientContext()
  const hasStatisticalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Statistical${name}`)),[api])

  if (!hasStatisticalEndpoint){
    return <></>
  }

  return <Chart {...props}/>
  

}

export default HistoryChart;