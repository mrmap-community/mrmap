import { BarChartProps, BarPlot, ChartContainer, ChartsLegend, ChartsTooltip, ChartsXAxis, ChartsYAxis } from '@mui/x-charts';
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
        field: 'dateCreated',
        order: 'DESC',
      },
      filter: {
        'service.id': record?.service?.id
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

  const timeFormatter = useCallback((seconds, short?: boolean = false) => {
      const hours = Math.floor(seconds / 3600); // 1 Stunde = 3600 Sekunden
      seconds = seconds % 3600; // Restsekunden nach Stunden
  
      const minutes = Math.floor(seconds / 60); // 1 Minute = 60 Sekunden
      seconds = seconds % 60; // Restsekunden nach Minuten
      const hoursStr = String(hours).padStart(2, '0');
      const minutesStr = String(minutes).padStart(2, '0');
      const secondsStr = String(seconds).padStart(2, '0');

      if (short) { 
        return `${hoursStr}H${minutesStr}M${secondsStr}S`
      };
      // Rückgabe im gewünschten Format
      return `${hours} Hours ${minutes} Minutes ${seconds} Seconds`;
  }, [])

  const props = useMemo<BarChartProps>(()=>{
    const fetchRecordDurationSeries = {
      type:'bar',
      id: 'fetchRecordDurationSeries',
      data: [] as number[],
      label: 'Total time to download all records',
      valueFormatter: (v) => timeFormatter(v, false),
    }
    const dbDurationAvgSeries = {
      type:'bar',
      id: 'dbDurationAvgSeries',
      data: [] as number[],
      label: 'Average time to handle records',
      valueFormatter: (v) => timeFormatter(v, false),
    }
    const dbDurationTotalSeries = {
      type:'bar',
      id: 'dbDurationTotalSeries',
      data: [] as number[],
      label: 'Total time to handle records',
      valueFormatter: (v) => timeFormatter(v, false),
      
    }
    const xAxis = {
      data: [] as RaRecord[],
      scaleType: 'band',
      valueFormatter: valueFormatter,
      
    }
    
    const _props: BarChartProps = {
      series: [fetchRecordDurationSeries,  dbDurationAvgSeries, dbDurationTotalSeries],
      xAxis: [xAxis],
      yAxis: [{valueFormatter: timeFormatter}],
    }
    record?.service && data?.forEach(record => {
      const fetchRecordDuration = parseDuration(record.fetchRecordDuration)

      fetchRecordDuration && fetchRecordDuration > 0 && fetchRecordDurationSeries.data.push(parseDuration(record.fetchRecordDuration))
      
      const mdToDbDuration = parseDuration(record.mdMetadataFileToDbDuration)
      mdToDbDuration && mdToDbDuration > 0 && dbDurationAvgSeries.data.push(mdToDbDuration / record.totalRecords)
      mdToDbDuration && mdToDbDuration > 0 && dbDurationTotalSeries.data.push(mdToDbDuration)

       xAxis.data.push(record)
    }) 

    return _props
  },[data])

  return (
    <ChartContainer
      series={props.series.filter(serie => serie.id === selectedSerie)}
      colors={mangoFusionPalette}
      height={400}
      margin={{top: 10, bottom: 30, left: 100, right: 10}}
      xAxis={props.xAxis}
      yAxis={props.yAxis}
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
      <ChartsYAxis

      />
    </ChartContainer >
  )

}

export default HarvestingJobTimingCharts