import { type AlertColor } from '@mui/material/Alert';
import { type ReactNode } from 'react';
import { RaRecord } from 'react-admin';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
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
  return (
    <ListGuesser
      resource='BackgroundProcess'
      updateFieldDefinitions={[
        {
          component: ProgressField, 
          props: {source: "progress", getColor: getColor}
        }
      ]}
      refetchInterval={5000}
    />

  )
}

export default ListBackgroundProcess
