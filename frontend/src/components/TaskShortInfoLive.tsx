import React, { type ReactNode, useCallback, useEffect, useState } from 'react'
import { type Identifier, type RaRecord, useDataProvider } from 'react-admin'

import Alert, { type AlertColor } from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import Box from '@mui/material/Box'
import LinearProgress, { type LinearProgressProps } from '@mui/material/LinearProgress'
import Typography from '@mui/material/Typography'
import { type CustomContentProps, SnackbarContent, useSnackbar } from 'notistack'

import { type CrudEvent } from '../providers/dataProvider'

const LinearProgressWithLabel = (props: LinearProgressProps & { value: number }): ReactNode => {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      <Box sx={{ width: '100%', mr: 1 }}>
        <LinearProgress variant="determinate" {...props} />
      </Box>
      <Box sx={{ minWidth: 35 }}>
        <Typography variant="body2" color="text.secondary">{`${Math.round(
          props.value
        )}%`}</Typography>
      </Box>
    </Box>
  )
}

const getColor = (status: string): AlertColor => {
  switch (status) {
    case 'successed':
      return 'success'
    case 'failed':
      return 'error'
    default:
      return 'info'
  }
}

export interface TaskShortInfoLiveProps extends CustomContentProps {
  taskId: Identifier
}

const TaskShortInfoLive = React.forwardRef<HTMLDivElement, TaskShortInfoLiveProps>(
  (props, ref) => {
    const {
      id,
      taskId
    } = props

    const dataProvider = useDataProvider()
    const { closeSnackbar } = useSnackbar()

    const [task, setTask] = useState<RaRecord>()

    const updateFromRealtimeBus = useCallback((message: CrudEvent) => {
      setTask(message.payload.records?.[0])
    }, [])

    useEffect(() => {
      // subscribe on mount
      dataProvider.subscribe(`resource/BackgroundProcess/${taskId}`, updateFromRealtimeBus)
      // unsubscribe on unmount
      return () => dataProvider.unsubscribe(`resource/BackgroundProcess/${taskId}`, updateFromRealtimeBus)
    }, [dataProvider])

    return (
      <SnackbarContent
        ref={ref}
      // role="alert"

      >
        <Alert
          severity={getColor(task?.status ?? '')}
          sx={{ width: '100%' }}
          title={task?.processType === 'registering' ? 'Register new Service' : 'Running Task'}
          onClose={() => { closeSnackbar(id) }}
        >
          <AlertTitle> {task?.processType === 'registering' ? 'Register new Service' : 'New Task'} </AlertTitle>

          {task?.status !== 'success' ? task?.phase : ''}
          <LinearProgressWithLabel
            value={task?.progress ?? 0}
            color={getColor(task?.status ?? '')}
          />
        </Alert>

      </SnackbarContent >
    )
  })

TaskShortInfoLive.displayName = 'TaskShortInfoLive'

export default TaskShortInfoLive
