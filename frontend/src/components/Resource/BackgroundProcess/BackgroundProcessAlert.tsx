import { type ReactNode, useMemo } from 'react'
import { useRecordContext } from 'react-admin'

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

  const { closeSnackbar } = useSnackbar()
  const record = useRecordContext()

  const title = useMemo(()=> {
    switch(record?.processType){
      case "registering":
        return "Register new Service"
      case "harvesting":
        return "Harvesting"
      case "monitoring":
        return "Monitoring"
      default:
        return "Running Task"
    }
  },[record])

  const stepInfo = useMemo(()=>{
    return record?.doneSteps && record?.totalSteps && `${record?.doneSteps ?? 0} of ${record?.totalSteps ?? 0} steps done.`
  }, [record])

  return (
    <Alert
      severity={getColor(record?.status ?? '')}
      sx={{ width: '100%' }}
      title={title}
      onClose={() => { closeSnackbar(snackId) }}
    >
      <AlertTitle> {title} </AlertTitle>

      {record?.status === 'completed' ? record?.status : record?.phase}<br/>
      {stepInfo}

      <LinearProgressWithLabel
        value={record?.progress ?? 0}
        color={getColor(record?.status ?? '')}
      />
    </Alert>
  )
}

export default BackgroundProcessAlert