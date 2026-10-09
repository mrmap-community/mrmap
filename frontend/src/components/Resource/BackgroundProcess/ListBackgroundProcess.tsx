import { type AlertColor } from '@mui/material/Alert';
import { type ReactNode } from 'react';
import { RaRecord } from 'react-admin';
import { ReadyState } from 'react-use-websocket';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import { useHttpClientContext } from '../../../context/HttpClientContext';
import ProgressField from '../../Field/ProgressField';


const getColor = (record: RaRecord): AlertColor => {
  switch (record?.status) {
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

const ListBackgroundProcess = (): ReactNode => {
  // the realtime bus reports every change of the listed processes, the interval
  // is only the fallback while it is not connected
  const { realtimeIsReady } = useHttpClientContext();
  return (
    <ListGuesser
      realtime={true}
      resource='BackgroundProcess'
      updateFieldDefinitions={[
        {
          component: ProgressField, 
          props: {source: "progress", getColor: getColor}
        }
      ]}
      refetchInterval={realtimeIsReady === ReadyState.OPEN ? false : 20000}
    />

  )
}

export default ListBackgroundProcess
