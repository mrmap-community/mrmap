import { RaRecord, RecordRepresentation, ShowButton, SimpleList, UrlField, useListContext, useRecordContext, useResourceContext, useResourceDefinition, useTranslate, WithRecord } from "react-admin";


import FiberManualRecordIcon from '@mui/icons-material/FiberManualRecord';
import { alpha, Card, CardContent, CardHeader, Chip, Grid, Stack, Typography } from "@mui/material";
import { PropsWithChildren, useCallback, useMemo } from "react";
import ListGuesser from "../../../../../jsonapi/components/ListGuesser";

import { format, isToday, isYesterday } from 'date-fns';
import { prepareGetCapabilititesUrl } from "../../../../../ows-lib/OwsContext/utils";
import HistoryList from "../../../../HistoryList";

const getDuration = (
  dateCreated: string,
  dateDone?: string,
) => {
  const created = new Date(dateCreated);
  return dateDone
        ? (new Date(dateDone).getTime() - created.getTime()) / 1000
        : undefined;
}

const formatMonitoringRun = (
    dateCreated: string,
    dateDone?: string,
) => {
    const created = new Date(dateCreated);

    const dateLabel = isToday(created)
        ? 'Today'
        : isYesterday(created)
          ? 'Yesterday'
          : format(created, 'dd.MM.yyyy');

    const timeLabel = format(created, 'HH:mm');

    const duration = getDuration(dateCreated, dateDone)

    return `${dateLabel}, ${timeLabel}${
        duration !== undefined ? ` · ${duration.toFixed(2)} s` : ''
    }`;
};



const WmsOverviewHeader = () =>{
  const record = useRecordContext()
  const {name} = useResourceDefinition()
  return (
    <Stack
      direction={{
        sm: "column",
        lg: "row",
      }}
      sx={{
        justifyContent: "space-between",
        alignItems: "flex-start",
      }}
    >
      <Stack>
        <Typography><RecordRepresentation/> <Chip variant="outlined" label={String(record?.version)?.split("").join(".")}/></Typography>
        <WithRecord 
          //label="show remote capabilities" 
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
      </Stack>
      <HistoryList
        resource={`Historical${name ?? ''}`}
        related={name ?? ''}
        record={record}
        
      />
    </Stack>
  )
}




const UpdateJobsCardBase = (
  {
    children
  }: PropsWithChildren
) => {
  const {data } = useListContext();
  const nestedResource = "WebMapServiceUpdateJob"
  const translate = useTranslate()
  const reviewRequired = useMemo(() => data?.some(record => record.statusCode === 2 || false),[data])
  
  return (
    <Card 
      variant="outlined" 
      sx={(theme) => ({
        border: 1,
        ...(reviewRequired ? {
          borderColor: 'warning.main',
        }: {
          borderColor: 'success.main',
        })})
      }
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
      />      
      <CardContent>
        {children}
      </CardContent>
    </Card>
  )
}


const UpdateJobsList = () => {
  const changes = useCallback((record: RaRecord)=>{
    const changes = []
    const newLayers = record?.mappings?.filter((mapping: RaRecord) => mapping.newLayer !== undefined && mapping.oldLayer === undefined)
    const deletedLayers = record?.mappings?.filter((mapping: RaRecord) => mapping.newLayer === undefined && mapping.oldLayer !== undefined)

    deletedLayers.length > 0 && changes.push(`${deletedLayers} layer(s) are marked for deletion`)
    newLayers.length > 0 && changes.push(`${newLayers.length || 0} new layer(s)`)

    return changes.join("·")
  },[])

  return (
    <SimpleList
        rightIcon={(record) => <ShowButton 
                                  label={record.status === 'Review required' ? 'Review' : 'View'}
                                  variant="contained" 
                                  color={record.status === 'Review required' ? 'warning' : 'primary'}
                                  icon={false}
                                /> 
        }
        primaryText={(record) => `Update #${record.id}`}
        secondaryText={record => `${record.status} | ${changes(record)}`}
        rowClick={false}
        sx={{
        p: 0,

        '& .MuiListItem-root': {
            px: 0,
            py: 0.5,
            minHeight: 32,
        },

        '& .MuiListItemText-root': {
            m: 0,
        },

        '& .MuiListItemButton-root': {
            py: 0,
        },
    }}
    />
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
  const queryOptions = {
    meta: {
      jsonApiParams: {
        include: 'mappings'
      }
    }
  }
  return (
    <ListGuesser
      resource={nestedResource}
      relatedResource={relatedResource}
      disableSyncWithLocation
      sort={{field:"doneAt", order:"DESC"}}
      filter={{"status_code__ne": 4}}
      queryOptions={queryOptions}
      actions={<></>}
      pagination={<></>}
      component={UpdateJobsCardBase}
      storeKey="wms_overview_update_jobs"
      defaultSelectedColumns={["id", "dateCreated", "doneAt", "status"]}
      dataGridProps={{
        component:UpdateJobsList
      }}
    />
  )
}



const MonitoringRunsCardBase = ({
  children
}: PropsWithChildren) => {
  const {data } = useListContext();
  const translate = useTranslate();

  const lastRun = data?.[0]
  return (
    <Stack spacing={2}>
      <Card 
        variant="outlined"
         sx={(theme) => (lastRun?.success ? {
            border: 1,
            borderColor: 'success.main',
        }: {
          border: 1,
          borderColor: 'warning.main',
        })}
      >
        <CardHeader
          title={"Last monitoring runs"}
          subheader={lastRun?.dateCreated && formatMonitoringRun(lastRun?.dateCreated, lastRun?.dateDone)}
          action={
            lastRun?.success ?
            <Chip
              size="small"
              color="success"
              variant="outlined"
              label={
                <Stack
                  direction="row"
                  sx={{
                    alignItems:"center"
                  }}
                >
                  <FiberManualRecordIcon
                    color={lastRun?.success ? 'success' : 'error'}
                    sx={{ fontSize: 12 }}
                    /> 
                  Passed
                </Stack>
              }
            />:
            <Chip
              size="small"
              color="error"
              label="Failed"
            />
          }
          sx={(theme) => (lastRun?.success ?{
              bgcolor: alpha(theme.palette.success.main, 0.08),
              borderColor: 'success.main',
            }:{
              bgcolor: alpha(theme.palette.success.main, 0.08),
              borderColor: 'warning.main',
          }
          )}
        />
         <CardContent>
          {children}
        </CardContent>
        
      </Card>
    </Stack>
  )
}

const MonitoringRunsList = () => {
  return (
    <SimpleList
        leftIcon={(record) => <FiberManualRecordIcon color={record.success? "success": "warning"}/>}
        rightIcon={(record) => `${record?.getMapProbeResults?.length + record?.getCapabilititesProbeResults?.length} checks, in ${getDuration(record?.dateCreated, record?.dateDone)?.toFixed(2)} s`}
        primaryText={(record) => `${formatMonitoringRun(record?.dateDone)}`}
        rowClick={false}
        sx={{
        p: 0,

        '& .MuiListItem-root': {
            px: 0,
            py: 0.5,
            minHeight: 32,
        },

        '& .MuiListItemText-root': {
            m: 0,
        },

        '& .MuiListItemButton-root': {
            py: 0,
        },
    }}
    />
  )
}


const MonitoringRunsCard = () => {
  const resource = useResourceContext()
  const nestedResource = "WebMapServiceMonitoringRun"
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
      sort={{field:"dateDone", order:"DESC"}}
      perPage={5}
      actions={<></>}
      pagination={<></>}
      component={MonitoringRunsCardBase}
      storeKey="wms_overview_monitoring_runs"
      defaultSelectedColumns={["id", "dateCreated", "dateDone", "status"]}
      dataGridProps={{
        component: MonitoringRunsList
      }}      
    />
  )
}


const OverviewtTab = () => {
  return (
    <Stack spacing={1}>
      <WmsOverviewHeader/>
      <Grid 
        container
        direction={"row"}
        sx={{
          alignItems: "stretch",
          justifyContent: "center",
        }}
      >
        <Grid size={6}>
          <UpdateJobsCard />
        </Grid>
        <Grid size={6}>
          <MonitoringRunsCard/>
        </Grid>
      </Grid>
    </Stack>
  )
}


export default OverviewtTab