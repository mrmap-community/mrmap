import { AllSeriesType, AreaPlot, ChartContainer, ChartContainerProps, ChartsLegend, ChartsTooltip, LineHighlightPlot, LinePlot, MarkPlot } from '@mui/x-charts';
import { mangoFusionPalette } from '@mui/x-charts/colorPalettes';
import { ChartSeriesType } from '@mui/x-charts/internals';
import { subDays } from 'date-fns';
import { useMemo } from 'react';
import { useGetList, useListContext, useResourceDefinition } from 'react-admin';
import { useHttpClientContext } from '../../../context/HttpClientContext';

const styles = {
  flex: { display: 'flex' },
  flexColumn: { display: 'flex', flexDirection: 'column' },
  leftCol: { flex: 1, marginRight: '0.5em' },
  rightCol: { flex: 1, marginLeft: '0.5em' },
  singleCol: { marginTop: '1em', marginBottom: '1em' },
};

interface TotalByDay {
  date: number;
  total: number;
}

const lastDay = new Date();
const lastMonthDays = Array.from({ length: 30 }, (_, i) => subDays(lastDay, i));
const aMonthAgo = subDays(new Date(), 30);

const dateFormatter = (date: number): string =>
    new Date(date).toLocaleDateString();



const Chart = (
  {
    ...props
  }: ChartContainerProps
) => {
  const { name } = useResourceDefinition()

  const { total } = useListContext();

  const { data } = useGetList(`Statistical${name}`, {sort: {field: "id", order: "DESC"}})

  const organizedData = useMemo(()=>{
      const _organizedData = data?.map((record, index) => {
        if (index === 0) {
          record["total"] = total
          return record
        }
        record["total"] = data[index-1]["total"] - data[index-1]["new"] + data[index-1]["deleted"]
        return record
      }).reverse() || []


      if (_organizedData !== undefined && _organizedData?.length > 0){
        // insert date - 1 day calculated result to provide initial data points
        const prevDate = new Date(_organizedData[0].day)
        prevDate.setDate(prevDate.getDate() - 1);
        const prevDateString = prevDate.toISOString()
        const record = {
          id: prevDateString,
          day: prevDateString,
          total: _organizedData[0].total - _organizedData[0].new,
          new: 0,
          deleted: 0,
          updated: 0,
        }
        _organizedData.unshift(record)
        
      }
      return _organizedData

  },[total, data])

  const series = useMemo<Readonly<AllSeriesType<ChartSeriesType>>[]>(() => {
    const newDataSeries: any[] = []
    const deletedDataSeries: any[] = []
    const updatedDataSeries: any[] = []
    const dailyTotal: any[] = []
    
    const series = [
      { type: 'line', data: dailyTotal, label: 'total', area: true, showMark: true},
      //{ type: 'line', data: newDataSeries, label:'new' ,},
      //{ type: 'line', data: deletedDataSeries, label:'deleted'},
      //{ type: 'line', data: updatedDataSeries, label:'updated'},
    ]
  
    organizedData?.forEach(data => {
      dailyTotal.push(data.total ?? 0)
      newDataSeries.push(data.new ?? 0)
      deletedDataSeries.push(data.deleted ?? 0)
      updatedDataSeries.push(data.updated ?? 0)
    })

    return series
  }, [organizedData])


  const xAxis = useMemo(()=>(
    [{
      scaleType: 'band',
      data: organizedData?.map(data => (data.id)) || [],
      id: 'x-axis-id',
      height: 45,
      position: 'none'
    }]
  ),[organizedData])

  

  return (
    <ChartContainer
        series={series}
        xAxis={xAxis}
        yAxis={[{
          width: 30,
          position: 'none'
        }]}
        //yAxis={[{ label: 'rainfall (mm)', width: 60 }]}
        colors={mangoFusionPalette}
        //height={300}
        margin={{
          left: 0,
          right: 0,
          
        }}
        {...props}
      >
        
        <AreaPlot />
        <LinePlot />
        <MarkPlot />
        <LineHighlightPlot />
        <ChartsLegend direction="horizontal" />
        <ChartsTooltip />
    </ChartContainer >
  )

}


const HistoryChart = (
  {
    ...props
  }: ChartContainerProps
) => {
  const { name } = useResourceDefinition()
  
  const { api } = useHttpClientContext()
  const hasStatisticalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Statistical${name}`)),[api])

  if (!hasStatisticalEndpoint){
    return <></>
  }

  return <Chart {...props}/>
  

}

export default HistoryChart;