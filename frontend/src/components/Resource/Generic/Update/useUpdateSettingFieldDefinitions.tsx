import { useResourceContext } from 'react-admin';

import useFieldsForResource from '../../../../jsonapi/hooks/useFieldsForResource';
import CronInput from '../../../Input/CronInput';


const useMonitoringUpdateFieldDefinitions = (

) => {
  const resource = useResourceContext()
  return useFieldsForResource({
    resource: resource, 
    overwrites: [{props: {source: 'scheduleInterval'}, component: CronInput}]
  })
} 


export default useMonitoringUpdateFieldDefinitions;