import { type ReactNode, useMemo } from 'react'
import { Link, useCreatePath, useRecordContext, useTranslate } from 'react-admin'

import Alert, { type AlertColor } from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import Box from '@mui/material/Box'
import LinearProgress, { type LinearProgressProps } from '@mui/material/LinearProgress'
import Typography from '@mui/material/Typography'
import { SnackbarKey, useSnackbar } from 'notistack'


export const LinearProgressWithLabel = (props: LinearProgressProps & { value: number }): ReactNode => {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      <Box sx={{ width: '100%', mr: 1 }}>
        <LinearProgress variant="determinate" {...props} />
      </Box>
      <Box sx={{ minWidth: 40 }}>
        <Typography variant="body2" color="text.secondary">{`${props.value.toFixed(2)}%`}</Typography>
      </Box>
    </Box>
  )
}

export const getColor = (status: string): AlertColor => {
  switch (status) {
    case 'completed':
    case 'successed':
      return 'success'
    case 'failed':
      return 'error'
    case 'running':
      return 'info'
    default:
      return 'info'
  }
}

export interface BackgroundProcessAlertProps {
  snackId: SnackbarKey
}

const BackgroundProcessAlert = (
  {
    snackId,
  }: BackgroundProcessAlertProps) => {
    
  const createPath = useCreatePath();
  const { closeSnackbar } = useSnackbar()
  const record = useRecordContext()
  const translate = useTranslate()

  const title = useMemo(()=> {
    switch(record?.processType){
      case "registering":
        return translate("resources.BackgroundProcess.titles.registering")
      case "harvesting": {
        const label = translate("resources.BackgroundProcess.titles.harvesting")
        const link = record.relatedId && <Link to={createPath({resource: "CatalogueService", type: "show", id: record.relatedId})}>{translate("resources.BackgroundProcess.titles.harvestingOf", { id: record.relatedId })}</Link>
        return link !== undefined ? link: label
      }
      case "monitoring":
        return translate("resources.BackgroundProcess.titles.monitoring")
      default:
        return translate("resources.BackgroundProcess.titles.runningTask")
    }
  },[record, translate, createPath])

  const info = useMemo(()=>{
    switch(record?.status){
      case "completed":
        return translate("resources.BackgroundProcess.states.completed")
      case "pending":
        return translate("resources.BackgroundProcess.states.waitingForSchedule")
      default:
        return record?.phase
    }
  },[record?.status, record?.phase, translate])

  const stepInfo = useMemo(()=>{
    return record?.doneSteps && record?.totalSteps && translate("resources.BackgroundProcess.stepsDone", { done: record?.doneSteps ?? 0, total: record?.totalSteps ?? 0 })
  }, [record, translate])

  return (
    <Alert
      severity={getColor(record?.status ?? '')}
      sx={{ width: '100%' }}
      title={title}
      onClose={() => { closeSnackbar(snackId) }}
    >
      <AlertTitle> {title} </AlertTitle>

      {info}<br/>
      {stepInfo}

      <LinearProgressWithLabel
        value={record?.progress ?? 0}
        color={getColor(record?.status ?? '')}
      />
    </Alert>
  )
}

export default BackgroundProcessAlert