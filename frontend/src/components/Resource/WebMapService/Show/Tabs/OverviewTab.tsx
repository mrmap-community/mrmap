import { SimpleShowLayout, useGetList, useRecordContext, useResourceContext } from "react-admin";

import { RaRecord, UrlField, WithRecord } from 'react-admin';
import { prepareGetCapabilititesUrl } from "../../../../../ows-lib/OwsContext/utils";


import Box from '@mui/material/Box';
import { LineChart, MarkElementProps } from '@mui/x-charts/LineChart';
import { Fragment } from "react/jsx-runtime";

const margin = { right: 24 };
const pData = [2400, 1398, 9800, 3908, 4800, 3800, 4300];
const xLabels = [
  'Page A',
  'Page B',
  'Page C',
  'Page D',
  'Page E',
  'Page F',
  'Page G',
];

const CustomMark = (props: MarkElementProps) => {
  const { x, y, color } = props;

  return (
    <g>
      <circle cx={x} cy={y} r={4} fill={color || 'currentColor'} />
      <text
        x={x}
        y={Number(y) - 12}
        style={{
          textAnchor: 'middle',
          dominantBaseline: 'auto',
          fill: color || 'currentColor',
          fontWeight: 'bold',
          fontSize: 12,
        }}
      >
        {pData[props.dataIndex].toString()}
      </text>
    </g>
  );
}

const CustomLabelChart = () => {
  return (
    <Box sx={{ width: '100%', height: 300 }}>
      <LineChart
        series={[{ data: pData, label: 'pv', showMark: true }]}
        xAxis={[{ scaleType: 'point', data: xLabels }]}
        yAxis={[{ width: 50 }]}
        margin={margin}
        slots={{
          mark: CustomMark,
        }}
      />
    </Box>
  );
}

const UpdateJobStats = () => {
  const record = useRecordContext()

  const {data} = useGetList(
    "HistoricalLayer",
    {
      filter: {
        //"history_change_reason__icontains": "updatejob_id: 2"
        //"history_date": "2026-09-18T11:46:40.704159+02:00"
      },
      meta: {
        // TODO: sparsefields
        
      }
    }
  )

  console.log(record, "history_data",data)

  return (
    <Fragment/>
  )
}


const OverviewtTab = () => {


  // Monitoring statistics
  // Update statistics
  // General State => isSearchable, isActive, isSecured, isSpatialSecured

  const record = useRecordContext()
  const resource = useResourceContext()

  const { data: monitoringRuns } = useGetList(
    "WebMapServiceMonitoringRun", 
    {
      meta: {
        relatedResource: {
          resource: resource,
          id: record?.id
        }
      }
    }
  )

  const { data: updateJobs } = useGetList(
    "WebMapServiceUpdateJob", 
    {
      sort: {field: 'doneAt', order: 'DESC'},
      meta: {
        relatedResource: {
          resource: resource,
          id: record?.id
        }
      }
    }
  )

  


  console.log(
    "updateJobas",
    updateJobs
  )


  return (
    <Fragment>
      <UpdateJobStats/>


      <SimpleShowLayout>
        <UrlField source="xmlBackupFile" label='show stored capabilitites'/>
        <WithRecord 
            label="show remote capabilities" 
            render={(record: RaRecord) => {
                const url = record.operationUrls?.find((operationUrl: RaRecord)=> (operationUrl.operation === 1 && operationUrl.method === 1));
                url.url = prepareGetCapabilititesUrl(
                        url.url,
                        "WMS",
                        record.version.toString().split('').join('.')
                    ).href
                return url ? <UrlField record={url} source="url"/> : null; 
            }}
        />
        <UrlField source="xmlBackupFileSecured" label='show secured capabilitites'/>
      </SimpleShowLayout>
    </Fragment>
  )
}


export default OverviewtTab