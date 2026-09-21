import useFieldsForResource from '../../../../jsonapi/hooks/useFieldsForResource';
import CronInput from '../../../Input/CronInput';


const useWebMapServiceMonitoringUpdateFieldDefinitions = () => {
  return useFieldsForResource({
    resource: 'WebMapServiceUpdateSetting', 
    overwrites: [{props: {source: 'scheduleInterval'}, component: CronInput}]
  })
} 


export default useWebMapServiceMonitoringUpdateFieldDefinitions;