import React from 'react'
import { type Identifier } from 'react-admin'

import { type CustomContentProps, SnackbarContent } from 'notistack'

import RealtimeShowContextProvider from '../../../jsonapi/components/Realtime/RealtimeShowContextProvider'
import BackgroundProcessAlert from './BackgroundProcessAlert'
import { IS_STALE_CHECK_INTERVAL, isStale } from './ShowBackgroundProcess'

export interface TaskShortInfoLiveProps extends CustomContentProps {
  taskId: Identifier
}

const SnackbarContentBackgroundProcess = React.forwardRef<HTMLDivElement, TaskShortInfoLiveProps>(
  (props, ref) => {
    const {
      id,
      taskId
    } = props

    return (
      <SnackbarContent
        ref={ref}
      >
        <RealtimeShowContextProvider
          isStaleCheckInterval={IS_STALE_CHECK_INTERVAL}
          isStale={isStale}
          id={taskId}
          resource='BackgroundProcess'
        >
          <BackgroundProcessAlert
            snackId={id}
          />
        </RealtimeShowContextProvider>

      </SnackbarContent >
    )
  })

SnackbarContentBackgroundProcess.displayName = 'TaskShortInfoLive'

export default SnackbarContentBackgroundProcess
