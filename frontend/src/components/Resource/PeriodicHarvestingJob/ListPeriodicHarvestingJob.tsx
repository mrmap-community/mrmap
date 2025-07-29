import { useMemo, type ReactNode } from 'react';
import { useRecordContext } from 'react-admin';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import EmptyList from '../../Lists/Empty';


const ListPeriodicHarvestingJob = (): ReactNode => {
  const record = useRecordContext();
  const relatedProps = useMemo(()=>{
    if (record !== undefined){
      return {
        resource: 'PeriodicHarvestingJob',
        relatedResource: 'CatalogueService',
        relatedResourceId: record.id
      }
    }
  },[record])

  return (
    <ListGuesser
      resource='PeriodicHarvestingJob'
      defaultSelectedColumns={['id', 'enabled', 'scheduling', 'timeUntilNextRun']}
      sort={{field: 'id', order: 'DESC'}}
      empty={<EmptyList defaultValue={{ service: { id: record?.id } }} />} 
      {...relatedProps}
    />

  )
}

export default ListPeriodicHarvestingJob
