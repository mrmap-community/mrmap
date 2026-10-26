import type { TimelineRecord } from './HistoryTimeline'

import { type ReactNode, useMemo } from 'react'
import {
  type RaRecord,
  RecordRepresentation,
  SimpleList,
  type SimpleListProps,
  useGetList,
  useLocaleState,
  useTranslate,
} from 'react-admin'
import { Link } from 'react-router-dom'

import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlineOutlined'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlineOutlined'
import HistoryIcon from '@mui/icons-material/History'
import UpdateIcon from '@mui/icons-material/Update'
import { Alert, Button, Typography } from '@mui/material'
import { camelCase, startCase } from 'lodash'

import { useSelectedRecordContext } from '../../../../jsonapi/components/SelectedRecordContext'
import ContextBasedDialog from '../../../Dialog/Dialog'
import { DialogBase, useDialogContextBase } from '../../../Dialog/DialogContextBase'
import HistoryEventDetails from './HistoryEventDetails'

const getIcon = (record: RaRecord): ReactNode => {
  if (record.historyType === 'created') {
    return <CheckCircleOutlineIcon color='success' fontSize='small' />
  } else if (record.historyType === 'deleted') {
    return <DeleteOutlineIcon color='error' fontSize='small' />
  }
  return <UpdateIcon color='info' fontSize='small' />
}

const fieldLabel = (field: string, related: string, translate: ReturnType<typeof useTranslate>): string => {
  const source = camelCase(field)
  return translate(`resources.${related}.fields.${source}`, {
    _: translate(`serviceShow.fields.${source}`, { _: startCase(field) }),
  })
}

/** Compact summary like "Title and 2 other fields changed", readable without the full values. */
const summaryText = (record: RaRecord, related: string, translate: ReturnType<typeof useTranslate>): string => {
  const changes = (record.delta ?? []) as { field: string }[]
  const event = translate(`historyList.${record.historyType}`, { _: record.historyType })
  if (changes.length === 0) return event
  const first = fieldLabel(changes[0].field, related, translate)
  const changesSummary = changes.length === 1
    ? translate('historyList.fieldChanged', { _: '%{field} changed', field: first })
    : translate('historyList.fieldsChanged', {
      _: '%{field} and %{smart_count} other fields changed',
      field: first,
      smart_count: changes.length - 1,
    })
  return record.historyType === 'updated' ? changesSummary : `${event} · ${changesSummary}`
}

interface PrimaryTextProps {
  record: RaRecord
  related: string
  selectedRecord: RaRecord | undefined
}

const PrimaryText = ({ record, related, selectedRecord }: PrimaryTextProps): ReactNode => {
  const translate = useTranslate()
  const text = summaryText(record, related, translate)

  return (
    <Typography component='span' variant='body2' noWrap sx={{ display: 'block' }}>
      {selectedRecord ? (
        text
      ) : (
        <>
          {record.title ?? (record.historyRelation
            ? <RecordRepresentation record={record.historyRelation} resource={related} />
            : record.id)}
          {' · '}{text}
        </>
      )}
    </Typography>
  )
}


export interface HistoryCompactFeedProps extends Omit<SimpleListProps, 'resource'> {
  /** Resource of the changed objects, used for field labels and the "view all" link. */
  related: string
  /** Historical resource to read; defaults to `Historical<related>`. */
  resource?: string
}

const HistoryFeed = ({
  related,
  resource = `Historical${related}`,
  sx,
  ...props
}: HistoryCompactFeedProps): ReactNode => {
  const { selectedRecord } = useSelectedRecordContext()
  const [locale] = useLocaleState()
  const translate = useTranslate()
  const { open, close } = useDialogContextBase()

  const jsonApiParams = useMemo(() => {
    const params: Record<string, string | number> = { include: 'historyUser' }
    params['fields[User]'] = 'username,string_representation'
    params['fields[HistoricalLayer]'] = 'history_type,history_date,history_user'
    if (selectedRecord?.id !== undefined) {
      params['filter[historyRelation]'] = selectedRecord.id
    }
    return params
  }, [selectedRecord?.id])

  const { data, total, isLoading, error } = useGetList(
    resource,
    {
      pagination: { page: 1, perPage: 10 },
      sort: { field: 'historyDate', order: 'DESC' },
      filter: { delta_size__gt: 0 },
      meta: { jsonApiParams }
    }
  )

  const openDetails = (record: RaRecord) => {
    open(
      `${translate(`historyList.${record.historyType}`, { _: record.historyType })} · ${new Date(record.historyDate).toLocaleString(locale)}`,
      <HistoryEventDetails event={record as TimelineRecord} related={related} />,
      <Button onClick={close}>{translate('ra.action.close', { _: 'Close' })}</Button>
    )
  }

  const viewAllTo = selectedRecord?.id !== undefined
    ? {
      pathname: `/${related}/history`,
      search: `?filter=${encodeURIComponent(JSON.stringify({ historyRelation: String(selectedRecord.id) }))}`,
    }
    : { pathname: `/${related}/history` }

  return (
    <>
      <SimpleList
        dense
        rowClick={(id, resource, record) => { openDetails(record); return false }}
        leftIcon={getIcon}
        primaryText={record => <PrimaryText record={record} related={related} selectedRecord={selectedRecord} />}
        secondaryText={record => (
          <Typography component="span" variant="caption">
            {[
              new Date(record.historyDate).toLocaleString(locale === 'en' ? 'en-GB' : locale, {
                day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
              }),
              record.historyUser?.username,
            ].filter(Boolean).join(' · ')}
          </Typography>
        )}
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
      {error ? (
        <Alert severity='error' sx={{ m: 1.5 }}>
          {translate('historyList.loadError', { _: 'Unable to load history.' })}
        </Alert>
      ) : !isLoading && (data ?? []).length === 0 ? (
        <Typography variant='body2' color='text.secondary' sx={{ px: 1.5, py: 2 }}>
          {translate('historyList.empty', { _: 'No changes recorded.' })}
        </Typography>
      ) : null}
      <Button component={Link} to={viewAllTo} size='small' startIcon={<HistoryIcon />} sx={{ m: 1.5 }}>
        {translate('historyList.viewAll', { _: 'View all history' })}
      </Button>
    </>
  )
}

const EventDialog = (): ReactNode => <ContextBasedDialog />

const HistoryCompactFeed = ({
  related,
  ...props
}: HistoryCompactFeedProps): ReactNode => (
  <DialogBase>
    <HistoryFeed related={related} {...props} />
    <EventDialog />
  </DialogBase>
)

export default HistoryCompactFeed
