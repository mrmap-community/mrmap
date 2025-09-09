import { type AlertColor } from '@mui/material/Alert';
import { useMemo, type ReactNode } from 'react';
import { RaRecord, SelectField, useRecordContext } from 'react-admin';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import ProgressField from '../../Field/ProgressField';


const getColor = (record: RaRecord): AlertColor => {
  switch(record.phase){
      case 4:
        return 'success';
      case 5:
        return 'error';
      case 0:
      default:
        return 'info';
    }
}

const ListHarvestingJob = (): ReactNode => {
  const record = useRecordContext();
  const relatedProps = useMemo(()=>{
    if (record !== undefined){
      return {
        resource: 'HarvestingJob',
        relatedResource: 'CatalogueService',
        relatedResourceId: record.id
      }
    }
  },[record])

  return (
    <ListGuesser
      realtime={true}
      resource='HarvestingJob'
      defaultSelectedColumns={['id', 'phase', 'progress', 'createdAt', 'doneAt']}
      sort={{field: 'id', order: 'DESC'}}
      perPage={5}
      updateFieldDefinitions={[
        {
          component: ProgressField, 
          props: {source: "progress", getColor: getColor}
        },
        {
          component: SelectField, 
          props: {source: "phase", choices: [{id:0, name: 'pending'}, {id:1, name: 'Get total records'}, {id:2, name: 'Download records'}, {id:3, name: 'Persisting records'}, {id:4, name: 'Completed'}, {id:5, name: 'Arborted'}, {id:4711, name: 'Abort'}]}
        }
      ]}
      refetchInterval={20000}
      {...relatedProps}
    />

  )
}

export default ListHarvestingJob
