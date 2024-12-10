import React, { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
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
    case 'running':
      return 'info'
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

    const title = useMemo(()=> {
      switch(task?.processType){
        case "registering":
          return "Register new Service"
        case "harvesting":
          return "Harvesting"
        case "monitoring":
          return "Monitoring"
        default:
          return "Running Task"
      }
    },[task])

    useEffect(() => {
      // subscribe on mount
      dataProvider.subscribe(`resource/BackgroundProcess/${taskId}`, updateFromRealtimeBus)
      // unsubscribe on unmount
      return () => dataProvider.unsubscribe(`resource/BackgroundProcess/${taskId}`, updateFromRealtimeBus)
    }, [dataProvider])

    return (
      <SnackbarContent
        ref={ref}
      >
        <Alert
          severity={getColor(task?.status ?? '')}
          sx={{ width: '100%' }}
          title={title}
          onClose={() => { closeSnackbar(id) }}
        >
          <AlertTitle> {title} </AlertTitle>

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
