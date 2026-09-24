import { LinearProgress, useGetList, useListContext, useRecordContext, useResourceContext, useTranslate } from "react-admin";



import { alpha, Card, CardContent, CardHeader, Chip, Grid, Stack, Typography } from "@mui/material";
import Box from '@mui/material/Box';
import { LineChart, MarkElementProps } from '@mui/x-charts/LineChart';
import { PropsWithChildren, useMemo } from "react";
import { Fragment } from "react/jsx-runtime";
import ListGuesser from "../../../../../jsonapi/components/ListGuesser";

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


const WmsOverviewHeader = () =>{
  const record = useRecordContext()

  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 6, md: 3 }}>
          <Card variant="outlined">
              <CardContent>
                  <Typography variant="overline" color="text.secondary">
                      Layers
                  </Typography>

                  <Typography variant="h4">
                      {record?.layers.length}
                  </Typography>

                  <Typography variant="caption" color="text.secondary">
                      2 changed remotely
                  </Typography>
              </CardContent>
          </Card>
      </Grid>
      <Grid size={{ xs: 6, md: 3 }}>
          <Card variant="outlined">
              <CardContent>
                  <Typography variant="overline" color="text.secondary">
                      Last update
                  </Typography>

                  <Typography variant="h6">
                      Today, 08:42
                  </Typography>

                  <Typography variant="caption" color="text.secondary">
                      Completed in 14 s
                  </Typography>
              </CardContent>
          </Card>
      </Grid>

      <Grid size={{ xs: 6, md: 3 }}>
          <Card
              variant="outlined"
              sx={{
                  borderColor: 'warning.main',
                  bgcolor: 'warning.50',
              }}
          >
              <CardContent>
                  <Typography variant="overline" color="warning.main">
                      Needs review
                  </Typography>

                  <Typography variant="h4">
                      2
                  </Typography>

                  <Typography variant="caption">
                      Open update jobs
                  </Typography>
              </CardContent>
          </Card>
      </Grid>

      <Grid size={{ xs: 6, md: 3 }}>
          <Card variant="outlined">
              <CardContent>
                  <Typography variant="overline" color="text.secondary">
                      Monitoring
                  </Typography>

                  <Chip
                      size="small"
                      color="success"
                      label="Healthy"
                  />
              </CardContent>
          </Card>
      </Grid>
    </Grid>
  )
}




const UpdateJobsCardBase = (
  {
    children
  }: PropsWithChildren
) => {
  const {data, isPending, error, meta } = useListContext();
  const nestedResource = "WebMapServiceUpdateJob"
  const translate = useTranslate()
  const reviewRequired = useMemo(() => data?.some(record => record.statusCode === 2 || false),[data])
  
  console.log(data,reviewRequired)
  return (
    <Card 
      variant="outlined" 
      sx={(theme) => (reviewRequired ? {
            border: 1,
            borderColor: 'warning.main',
        }: {
          border: 1,
          borderColor: 'success.main',
        })}
    >
      <CardHeader
        title={
          reviewRequired ? translate(`resources.${nestedResource}.reviewRequired`): translate(`resources.${nestedResource}.lastUpdateJobs`)
        }
        subheader={
          reviewRequired ? translate(`resources.${nestedResource}.reviewRequiredSubheader`): translate(`resources.${nestedResource}.lastUpdateJobsSubheader`)
        }
        action={
          reviewRequired? 
          <Chip
            size="small"
            color="warning"
            label="1 open"
          />:
          <Chip
            size="small"
            color="success"
            label={data?.[0].doneAt}
          />
        }
        severity="warning"
        sx={(theme) => (reviewRequired ?{
            bgcolor: alpha(theme.palette.warning.main, 0.08),
            borderColor: 'warning.main',
        }:{
          bgcolor: alpha(theme.palette.success.main, 0.08),
          borderColor: 'success.main',
        }
      )}
      >
        
      </CardHeader>
      
    <CardContent>
      {children}
     



      {
        /*
        <List disablePadding>
        <ListItem
            divider
            secondaryAction={
                <Button
                    variant="contained"
                    size="small"
                >
                    Review changes
                </Button>
            }
        >
            <ListItemText
                primary={
                    <Stack direction="row" spacing={1} sx={{
              alignItems:"center"
            }}>
                        <Typography >
                            Update #1842
                        </Typography>

                        <Chip
                            label="Manual review"
                            size="small"
                        />const { isPending, error, meta } = useListContext();
                    </Stack>
                }
                secondary="3 layer changes · 1 new layer · metadata changed"
            />
        </ListItem>
    </List>
        */
      }
      </CardContent>

</Card>
  )
}

const UpdateJobsCard = () => {
  const resource = useResourceContext()
  const nestedResource = "WebMapServiceUpdateJob"
  const record = useRecordContext()
  const relatedResource = {
    resource: resource,
    id: record?.id
  }
  return (
    <ListGuesser
      resource={nestedResource}
      relatedResource={relatedResource}
      disableSyncWithLocation
      sort={{field:"doneAt", order:"DESC"}}
      filter={{"status_code__ne": 4}}
      actions={<></>}
      pagination={<></>}
      component={UpdateJobsCardBase}
      
      defaultSelectedColumns={["id", "dateCreated", "doneAt", "status"]}
    />
  )
}


const MonitoringOverview = () => {
  return (

    <Stack spacing={2}>
      <Stack
          direction="row"
          spacing={2}
          sx={{
            alignItems:"center"
          }}
      >
          <Typography sx={{ width: 130 }}>
              GetCapabilities
          </Typography>

          <LinearProgress
              variant="determinate"
              value={38}
              color="success"
              sx={{ flex: 1 }}
          />

          <Typography sx={{ width: 70, textAlign: 'right' }}>
              462 ms
          </Typography>
      </Stack>

      <Stack
          direction="row"
          spacing={2}
          sx={{
            alignItems:"center"
          }}
      >
          <Typography sx={{ width: 130 }}>
              GetMap
          </Typography>

          <LinearProgress
              variant="determinate"
              value={71}
              color="success"
              sx={{ flex: 1 }}
          />

          <Typography sx={{ width: 70, textAlign: 'right' }}>
              891 ms
          </Typography>
      </Stack>
    </Stack>
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





  return (
    <Stack spacing={3}>

      <WmsOverviewHeader/>

      <UpdateJobsCard/>
      <MonitoringOverview/>


{
/*
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

    <RecordContext
      value={reviewRequiered?.[0]}
    >
      <SimpleShowLayout
      >
        <TextField source="status" />

      </SimpleShowLayout>
    </RecordContext>
    */
}
    </Stack>
  )
}


export default OverviewtTab