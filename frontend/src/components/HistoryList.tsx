import { type ReactNode, useMemo } from 'react'
import { type RaRecord, RecordRepresentation, SimpleList, type SimpleListProps, useGetList, useGetRecordRepresentation } from 'react-admin'

import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import UpdateIcon from '@mui/icons-material/Update'
import { Box, CardHeader, Chip, Typography } from '@mui/material'

const getIcon = (record: RaRecord): ReactNode => {
  if (record.historyType === 'created') {
    return <CheckCircleOutlineIcon color='success' />
  } else if (record.historyType === 'updated') {
    return <UpdateIcon color='info' />
  } else if (record.historyType === 'deleted') {
    return <DeleteOutlineIcon color='error' />
  }
}

const getTertiaryText = (record: RaRecord): ReactNode => {
   
  return `${new Date(record.historyDate).toLocaleString('de-DE')}, by ${record.historyUser?.username}`
}

export interface PrimaryTextProps {
  record: RaRecord
  related: string
  selectedRecord: RaRecord | undefined
}

const PrimaryText = ({ record, related, selectedRecord }: PrimaryTextProps): ReactNode => {
  const changedFields = record.delta?.map((change: any, index: number) => <Typography key={`${record.id}-change-${index}`} sx={{ p: 1 }}>{change.field} changed from {change.old} to {change.new}</Typography>)

  const primaryText = useMemo(() => {
    if (selectedRecord !== undefined) {
      if (record.historyType === 'created') {
        return 'Created'
      } else {
        return (
          <Box>
            <Chip
              label={record.delta?.length ?? 0}
            />
            {changedFields}

          </Box>
        )
      }
    } else if (record.historyType === 'deleted') {
       
      return `${record.title} (${record.historyRelation.id})`
    } else {
      return <RecordRepresentation record={record.historyRelation} resource={related} />
    }
  }, [])

  return primaryText
}

export interface HistoryListProps extends SimpleListProps {
  related: string
  record: RaRecord | undefined
}

const HistoryList = ({
  related,
  record: selectedRecord,

  ...props
}: HistoryListProps): ReactNode => {
  const jsonApiParams = useMemo(() => {
    const params: any = { include: 'historyUser,historyRelation' }
    // params[`fields[${related ?? ''}]`] = 'title'
    params['fields[User]'] = 'username,stringRepresentation'
    if (selectedRecord !== undefined) {
      params['filter[historyRelation]'] = selectedRecord.id
    }
    return params
  }, [props.resource, selectedRecord])

  const { data, total, isLoading } = useGetList(
    props.resource ?? '',
    {
      pagination: { page: 1, perPage: 10 },
      sort: { field: 'historyDate', order: 'DESC' },
      meta: { jsonApiParams }
    }

  )
  const getRecordRepresentation = useGetRecordRepresentation(related)

  return (

      <CardHeader
        title={(selectedRecord === undefined) ? 'Last 10 events' : getRecordRepresentation(selectedRecord)}
        subheader={
          <SimpleList
            leftIcon={record => getIcon(record)}
            primaryText={record => <PrimaryText record={record} related={related} selectedRecord={selectedRecord} />}
            tertiaryText={record => getTertiaryText(record)}
            linkType={false}
            // rowSx={record => ({ backgroundColor: record.historyType === 'created' ? '#efe' : 'white' })}
            data={data}
            isLoading={isLoading}
            total={total}
            // sx={{ overflowY: 'scroll' }}
            
            {...props}
          />
        }
      >

      </CardHeader>

  )
}

export default HistoryList
