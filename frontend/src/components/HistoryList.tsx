import { type ReactNode, useMemo } from 'react'
import { type RaRecord, RecordRepresentation, SimpleList, type SimpleListProps, useGetList, useLocaleState, useTranslate } from 'react-admin'

import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlineOutlined'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlineOutlined'
import UpdateIcon from '@mui/icons-material/Update'
import { Tooltip, Typography } from '@mui/material'
import { useSelectedRecordContext } from '../jsonapi/components/SelectedRecordContext'

const getIcon = (record: RaRecord): ReactNode => {
  if (record.historyType === 'created') {
    return <CheckCircleOutlineIcon color='success' fontSize='small' />
  } else if (record.historyType === 'deleted') {
    return <DeleteOutlineIcon color='error' fontSize='small' />
  }
  return <UpdateIcon color='info' fontSize='small' />
}

interface HistoryChange {
  field: string
  old: unknown
  new: unknown
}

const formatValue = (value: unknown): string =>
  typeof value === 'string' ? value : JSON.stringify(value) ?? '—'

export interface PrimaryTextProps {
  record: RaRecord
  related: string
  selectedRecord: RaRecord | undefined
}

const PrimaryText = ({ record, related, selectedRecord }: PrimaryTextProps): ReactNode => {
  const translate = useTranslate()
  const changes = (record.delta ?? []) as HistoryChange[]
  const event = translate(`historyList.${record.historyType}`, { _: record.historyType })
  const details = changes.map(change =>
    `${change.field}: ${formatValue(change.old)} → ${formatValue(change.new)}`
  ).join('\n')

  return (
    <Tooltip title={details} slotProps={{ tooltip: { sx: { whiteSpace: 'pre-line' } } }}>
      <Typography component='span' variant='body2' noWrap sx={{ display: 'block' }}>
        {selectedRecord ? (
          <>{event}{changes.length > 0 && ` · ${changes.map(change => change.field).join(', ')}`}</>
        ) : (
          <>
            {record.title ?? (record.historyRelation
              ? <RecordRepresentation record={record.historyRelation} resource={related} />
              : record.id)}
            {' · '}{event}
          </>
        )}
      </Typography>
    </Tooltip>
  )
}

export interface HistoryListProps extends SimpleListProps {
  related: string
  record: RaRecord | undefined
}

const HistoryList = ({
  related,
  record: _record,
  sx,
  ...props
}: HistoryListProps): ReactNode => {
  const { selectedRecord } = useSelectedRecordContext()
  const [locale] = useLocaleState()
  const jsonApiParams = useMemo(() => {
    const params: Record<string, string | number> = { include: 'historyUser' }
    params['fields[User]'] = 'username,string_representation'
    params['fields[HistoricalLayer]'] = 'history_type,history_date,history_user'
    if (selectedRecord?.id !== undefined) {
      params['filter[historyRelation]'] = selectedRecord.id
    }
    return params
  }, [selectedRecord?.id])

  const { data, total, isLoading } = useGetList(
    props.resource ?? '',
    {
      pagination: { page: 1, perPage: 10 },
      sort: { field: 'historyDate', order: 'DESC' },
      filter: { delta_size__gt: 0 },
      meta: { jsonApiParams }
    }
  )

  return (
    <SimpleList
      dense
      rowClick={false}
      leftIcon={getIcon}
      primaryText={record => <PrimaryText record={record} related={related} selectedRecord={selectedRecord} />}
      secondaryText={record => [
        new Date(record.historyDate).toLocaleString(locale),
        record.historyUser?.username,
      ].filter(Boolean).join(' · ')}
      data={data}
      isLoading={isLoading}
      total={total}
      {...props}
      sx={[
        {
          py: 0,
          '& .MuiListItem-root, & .MuiListItemButton-root': { py: 0.75, px: 1.5 },
          '& .MuiListItemIcon-root': { minWidth: 32 },
          '& .MuiListItemText-root': { my: 0, minWidth: 0 },
          '& .MuiListItemText-secondary': {
            fontSize: '0.75rem',
            lineHeight: 1.5,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          },
          '& .MuiListItem-root + .MuiListItem-root': { borderTop: 1, borderColor: 'divider' },
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    />
  )
}

export default HistoryList
