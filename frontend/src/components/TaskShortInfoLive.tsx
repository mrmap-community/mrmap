import React, { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { type Identifier, type RaRecord, useDataProvider } from 'react-admin'

import Alert, { type AlertColor } from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import Box from '@mui/material/Box'
import LinearProgress, { type LinearProgressProps } from '@mui/material/LinearProgress'
import Typography from '@mui/material/Typography'
import { type CustomContentProps, SnackbarContent, useSnackbar } from 'notistack'

import { type CrudEvent } from '../providers/dataProvider'

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

    const [task, setTask] = useState<RaRecord | undefined>()
    

    const updateFromRealtimeBus = useCallback((message: CrudEvent) => {
      setTask(message.payload.records?.[0])
    }, [])

    const updateFromRestApi = useCallback(()=> {
      dataProvider.getOne("BackgroundProcess", {id: taskId}).then(({data}) => {
        if (task === undefined){
          setTask(data)
        }
      })
    }, [dataProvider, taskId, task, setTask])

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

    const stepInfo = useMemo(()=>{
      return task?.doneSteps && task?.totalSteps && `${task?.doneSteps} of ${task?.totalSteps} steps done.`
    }, [task])

    useEffect(() => {
      // subscribe on mount
      dataProvider.subscribe(`resource/BackgroundProcess/${taskId}`, updateFromRealtimeBus)
      // initial from remote api on mount
      updateFromRestApi()

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

          {task?.status !== 'success' ? task?.phase : ''}<br/>
          {stepInfo}
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
