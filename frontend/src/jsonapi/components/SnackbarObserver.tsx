import { type ReactNode, useCallback, useEffect } from 'react'
import { useDataProvider } from 'react-admin'

import { useSnackbar } from 'notistack'

import { type CrudEvent } from '../../providers/dataProvider'

const SnackbarObserver = (): ReactNode => {
  const dataProvider = useDataProvider()
  const { enqueueSnackbar } = useSnackbar()

  const handleBusEvent = useCallback((event: CrudEvent) => {
    event.payload.ids.forEach(id => {
      enqueueSnackbar('', {
        variant: 'taskProgress',
        persist: true,
        taskId: id
      })
    })
  }, [enqueueSnackbar])

  useEffect(() => {
    // subscribe on mount
    dataProvider.subscribe('resource/BackgroundProcess', handleBusEvent)
    // unsubscribe on unmount
    return () => dataProvider.unsubscribe('resource/BackgroundProcess', handleBusEvent)
  }, [dataProvider, handleBusEvent])

  return (
    <></>
  )
}

export default SnackbarObserver
