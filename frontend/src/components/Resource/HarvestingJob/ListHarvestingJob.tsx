import { type AlertColor } from '@mui/material/Alert';
import { useMemo, type ReactNode } from 'react';
import { RaRecord, useRecordContext } from 'react-admin';
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
      
      updateFieldDefinitions={[
        {
          component: ProgressField, 
          props: {source: "progress", getColor: getColor}
        }
      ]}
      refetchInterval={20000}
      {...relatedProps}
    />

  )
}

export default ListHarvestingJob
