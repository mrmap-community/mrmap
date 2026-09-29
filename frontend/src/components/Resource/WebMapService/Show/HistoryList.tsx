import { type ReactNode, useMemo, useState } from 'react'
import { type RaRecord, RecordContext, type SimpleListProps, useGetList, useRecordContext, useTranslate } from 'react-admin'

import CheckIcon from '@mui/icons-material/Check'
import DeleteIcon from '@mui/icons-material/Delete'
import UpdateIcon from '@mui/icons-material/Update'

import { alpha, Box, Card, CardContent, CardHeader, Chip, FormControl, MenuItem, Select, Typography } from '@mui/material'

import { TimelineDot, TimelineOppositeContent } from '@mui/lab'
import Timeline from '@mui/lab/Timeline'
import TimelineConnector from '@mui/lab/TimelineConnector'
import TimelineContent from '@mui/lab/TimelineContent'
import TimelineItem from '@mui/lab/TimelineItem'
import TimelineSeparator from '@mui/lab/TimelineSeparator'

import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Stack
} from '@mui/material'


export interface PrimaryTextProps {
  record: RaRecord
  related: string
  selectedRecord: RaRecord | undefined
}


export interface HistoryListProps extends SimpleListProps {
  related: string
  record: RaRecord | undefined
}
export interface Change {
    field: string;
    oldValue?: string | null;
    newValue?: string | null;
}
interface ChangeCardProps {
    defaultExpanded?: boolean;
}


interface DiffValueProps {
    label: string;
    value?: string | null;
    color: 'error' | 'success';
}

const DiffValue = ({
    label,
    value,
    color,
}: DiffValueProps) => (
    <Box
        sx={{
            flex: 1,
            minWidth: 0,
            p: 2,
            borderRadius: 1,
            bgcolor: theme =>
                color === 'error'
                    ? `${theme.palette.error.main}0D`
                    : `${theme.palette.success.main}0D`,
        }}
    >
        <Typography
            variant="caption"
            color="text.secondary"
            sx={{
              display:"block",
              mb:0.5
            }}
        >
            {label}
        </Typography>

        <Box
            sx={{
                p: 1,
                borderRadius: 0.5,
                bgcolor: theme =>
                    color === 'error'
                        ? `${theme.palette.error.main}18`
                        : `${theme.palette.success.main}18`,
                color: `${color}.main`,
                fontFamily: 'monospace',
                whiteSpace: 'pre-wrap',
                overflowWrap: 'anywhere',
            }}
        >
            {String(value) ?? '—'}
        </Box>
    </Box>
);

const ChangeDiff = ({ change }: { change: Change }) => (
  
    <Box>
        <Chip
            label={change.field}
            size="small"
            sx={{ mb: 1 }}
        />

        <Stack
            direction={{
                xs: 'column',
                md: 'row',
            }}
            spacing={2}
        >
            <DiffValue
                label="Previous value"
                value={change.oldValue}
                color="error"
            />

            <DiffValue
                label="New value"
                value={change.newValue}
                color="success"
            />
        </Stack>
    </Box>
);

export const ChangeCard = ({
    defaultExpanded = false,
}: ChangeCardProps) => {
    const record = useRecordContext()

    const changes = useMemo<Change[]>(
      () => (record?.delta?.map((change: any, index: number) => ({field: change.field, oldValue: change.old, newValue: change.new})) ?? []),
    [record])

    return (<Accordion
        defaultExpanded={defaultExpanded}
        disableGutters
        variant="outlined"
        sx={{
            borderRadius: 1,
            '&:before': {
                display: 'none',
            },
            '&:first-of-type': {
                borderRadius: 1,
            },
            '&:last-of-type': {
                borderRadius: 1,
            },
        }}
    >
        <AccordionSummary
          expandIcon={
           changes.length > 0 ? 
           <ExpandMoreIcon /> :
           null
          }
        >
          <Box>
              <Typography variant="subtitle1" sx={{fontWeight:600}}>
                  {record?._type} ({record?.historyRelation?.id})
              </Typography>
              {
                changes.length > 0 ?
                <Typography variant="body2" color="text.secondary">
                    {`${changes.length} ${changes.length === 1 ? 'change' : 'changes'}`}
                </Typography>:
                null
              } 
          </Box>
        </AccordionSummary>

        {changes.length > 0 && (
            <AccordionDetails>
                <Stack spacing={2}>
                    {changes.map(change => (
                        <ChangeDiff
                            key={change.field}
                            change={change}
                        />
                    ))}
                </Stack>
            </AccordionDetails>
        )}
    </Accordion>
    )
};


const ChangelogEntry = () => {
  const record = useRecordContext()
  const date = new Date(record?.historyDate)

  const icon = useMemo(()=>{
    switch(record?.historyType){
      case "created":
        return <CheckIcon fontSize="small" />
      case "updated":
        return <UpdateIcon fontSize="small" />
      default:
        return <DeleteIcon fontSize="small"/>
    }
  },[record?.historyType])

  const color = useMemo(()=>{
    switch(record?.historyType){
      case "created":
        return "success"
      case "updated":
        return "info"
      default:
        return "error"
    }
  },[record?.historyType])

  return (
    <TimelineItem>
      <TimelineOppositeContent
            color="text.secondary"
            sx={{
                flex: 0.12,
                minWidth: 130,
                pt: 1.5,
            }}
        >
            <Typography variant="body2">
                {date.toDateString()}
            </Typography>

            <Typography variant="caption">
                {date.toLocaleTimeString()}
            </Typography>
            {
              record?.historyUser ?
              <Typography variant="caption"sx={{ display:"block"}}>
                by {record?.historyUser?.username}
            </Typography>: null
            }
            
        </TimelineOppositeContent>
      
      <TimelineSeparator>
        
         <TimelineDot
            variant="outlined"
            color={color}
          >
              {icon}
          </TimelineDot>

        <TimelineConnector />
      </TimelineSeparator>
      <TimelineContent sx={{ pb: 3 }}>
         <ChangeCard/>
      </TimelineContent>
    </TimelineItem>
  )
}

const HistoryList = ({
  record,
  ...props
}: HistoryListProps): ReactNode => {

  const translate = useTranslate()
  const recordContext = useRecordContext(record)
  
  const wmsJsonApiParams = useMemo(() => {
    const params: any = { include: 'historyUser' }
    params['fields[User]'] = 'username,string_representation'
    if (recordContext !== undefined && recordContext.id !== undefined) {
      params['filter[historyRelation]'] = recordContext.id
    }
    return params
  }, [recordContext])

  const layerJsonApiParams = useMemo(() => {
    const params: any = { 
      include: 'historyUser' 
    }
    params['fields[HistoricalLayer]'] = 'history_type,delta,history_date,history_relation,title'
    params['fields[User]'] = 'username,string_representation'
    if (recordContext !== undefined && recordContext.id !== undefined) {
      params['filter[service]'] = recordContext.id
    }
    return params
  }, [recordContext])


  const {data: wmsChanges} = useGetList(
    "HistoricalWebMapService",
    {
      filter: {
        "changed_or_created": true,
      },
      sort: {
        field: "historyDate", 
        order: "DESC"
      },
      pagination: {
        page: 1,
        perPage: 100
      },
      meta: {
        jsonApiParams: wmsJsonApiParams
      }
    }
  )
  const {data: layerChanges} = useGetList(
    "HistoricalLayer",
    {
      filter: {
        "changed_or_deleted": true,
      },
      sort: {
        field: "historyDate", 
        order: "DESC"
      },
      pagination: {
        page: 1,
        perPage: 100
      },
      meta: {
        jsonApiParams: layerJsonApiParams
      }
    }
  )

const mixedChanges = useMemo(() => {
  return [
    ...(wmsChanges
      ?.filter(record => (record.delta?.length || 0) > 0 || record.historyType === "created")
      .map(record => ({
        ...record,
        _type: 'WebMapService' as const,
      })) ?? []),

    ...(layerChanges
      ?.filter(record => (record.delta?.length || 0) > 0  || record.historyType === "deleted")
      .map(record => ({
        ...record,
        _type: 'Layer' as const,
      })) ?? []),
  ].sort(
    (a, b) =>
      new Date(b.historyDate).getTime() -
      new Date(a.historyDate).getTime()
  );
}, [wmsChanges, layerChanges]);

  type ChangeType = 'all' | 'WebMapService' | 'Layer';

  const [changeType, setChangeType] =
      useState<ChangeType>('all');

  const filteredChanges = useMemo(
      () =>
          mixedChanges.filter(
              change =>
                  changeType === 'all' ||
                  change._type === changeType
          ),
      [mixedChanges, changeType]
  );

  return (
    <Card 
      variant="outlined" 
      
      sx={{
        border: 1,
        borderColor: 'secondary.main',
        
      }}
    >
      <CardHeader
        title={
          translate(`resources.ChangeLog.lastChanges`)
        }
        subheader={
          "Changes to this Web Map Service and related resources."
        }
        avatar={<UpdateIcon/>}
        action={
          <FormControl size="small">
            <Select
                value={changeType}
                onChange={event =>
                    setChangeType(event.target.value as ChangeType)
                }
                sx={{ minWidth: 180 }}
            >
                <MenuItem value="all">
                    All changes ({mixedChanges.length})
                </MenuItem>

                <MenuItem value="WebMapService">
                    Service changes ({wmsChanges?.length || 0})
                </MenuItem>

                <MenuItem value="Layer">
                    Layer changes ({layerChanges?.length || 0})
                </MenuItem>
            </Select>
        </FormControl>
        }
        severity="secondary"
        sx={(theme) => ({
            bgcolor: alpha(theme.palette.secondary.main, 0.08),
            borderColor: 'secondary.main',
          }
        )}
      />      
      <CardContent>
        <Timeline position="left">
          {
            filteredChanges?.map((record: RaRecord) => (
              <RecordContext value={record}>
                <ChangelogEntry />
              </RecordContext>
            ))
          }
    </Timeline>
      </CardContent>
    </Card>
    
  )
}


/**
 * 
 * <List
      resource={props.resource ?? ''}
      perPage={10}
      sort={{ field: 'historyDate', order: 'DESC' }}
      queryOptions={{
        meta: { jsonApiParams }
      }}
      exporter={false}
      pagination={false}
      component={ChangelogCardBase}
    >
      <Changelog/>
    </List>
 */
export default HistoryList
