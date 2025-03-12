import { BarChartProps, BarPlot, ChartsLegend, ChartsTooltip, ChartsXAxis, ChartsYAxis, ResponsiveChartContainer } from '@mui/x-charts';
import { mangoFusionPalette } from '@mui/x-charts/colorPalettes';
import { useCallback, useMemo } from 'react';
import { RaRecord, useGetList, useGetRecordRepresentation, useRecordContext } from 'react-admin';
import { parseDuration } from '../../../jsonapi/utils';


export interface HarvestingJobTimingChartsProps {
  selectedSerie: 'fetchRecordDurationSeries' | 'dbDurationAvgSeries' | 'dbDurationTotalSeries'
  withLegend?: boolean 
}

const HarvestingJobTimingCharts = (
  {
    selectedSerie,
    withLegend
  }: HarvestingJobTimingChartsProps
) => {
  const record = useRecordContext();

  const {data} = useGetList(
    'HarvestingJob',
    {
      pagination: {
        page: 1,
        perPage: 5,
      },
      sort: {
        field: 'backgroundProcess.dateCreated',
        order: 'DESC',
      },
      filter: {
        'service.id': record?.service.id
      },
      meta: {
        jsonApiParams:{
          'fields[HarvestingJob]': 'total_records,fetch_record_duration,md_metadata_file_to_db_duration',
        },
      }
    }
  );
  const getRecordRepresentation = useGetRecordRepresentation('HarvestingJob');
  
  const valueFormatter = useCallback((record: RaRecord, context) => {
    return getRecordRepresentation(record)
  },[getRecordRepresentation])

  const props = useMemo<BarChartProps>(()=>{
    const fetchRecordDurationSeries = {
      type:'bar',
      id: 'fetchRecordDurationSeries',
      data: [] as number[],
      label: 'Total time to download all records',
    }
    const dbDurationAvgSeries = {
      type:'bar',
      id: 'dbDurationAvgSeries',
      data: [] as number[],
      label: 'Average time to handle records',
    }
    const dbDurationTotalSeries = {
      type:'bar',
      id: 'dbDurationTotalSeries',
      data: [] as number[],
      label: 'Total time to handle records',
    }
    const xAxis = {
      data: [] as RaRecord[],
      scaleType: 'band',
      valueFormatter: valueFormatter,
      
    }
    
    const _props: BarChartProps = {
      series: [fetchRecordDurationSeries,  dbDurationAvgSeries, dbDurationTotalSeries],
      xAxis: [xAxis],
      //yAxis: [{ id: 'fetchRecordDurationSeries', scaleType: 'log'}, { id: 'dbDurationSeries', scaleType: 'log'}],
    }
    data?.forEach(record => {
      const fetchRecordDuration = parseDuration(record.fetchRecordDuration)
      fetchRecordDuration && fetchRecordDuration > 0 && fetchRecordDurationSeries.data.push(parseDuration(record.fetchRecordDuration))
      
      const mdToDbDuration = parseDuration(record.mdMetadataFileToDbDuration)
      mdToDbDuration && mdToDbDuration > 0 && dbDurationAvgSeries.data.push(mdToDbDuration / record.totalRecords)
      mdToDbDuration && mdToDbDuration > 0 && dbDurationTotalSeries.data.push(mdToDbDuration)

       xAxis.data.push(record)
    }) 

    return _props
  },[data])
  console.log(props.series.filter(serie => serie.id === selectedSerie))
  return (
    <ResponsiveChartContainer
      series={props.series.filter(serie => serie.id === selectedSerie)}
      colors={mangoFusionPalette}
      height={400}
      margin={{top: 10, bottom: 30, left: 40, right: 10}}
      xAxis={props.xAxis}
    >
      <BarPlot/>
      <ChartsTooltip 
        trigger="item"
      />
      {withLegend ? 
        <ChartsLegend 
          direction="row" 
          position={{horizontal: 'middle', vertical: 'top'}} 
        />: null
      }
      
      <ChartsXAxis/>
      <ChartsYAxis/>
    </ ResponsiveChartContainer >
  )

}

export default HarvestingJobTimingCharts