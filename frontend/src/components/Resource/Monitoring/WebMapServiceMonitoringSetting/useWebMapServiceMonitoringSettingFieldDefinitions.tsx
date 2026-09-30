import useFieldsForResource from '../../../../jsonapi/hooks/useFieldsForResource';
import CronInput from '../../../Input/CronInput';


const useWebMapServiceMonitoringSettingFieldDefinitions = () => {
  return useFieldsForResource({
    resource: 'WebMapServiceMonitoringSetting', 
    overwrites: [{props: {source: 'scheduleInterval'}, component: CronInput}]
  })
} 


export default useWebMapServiceMonitoringSettingFieldDefinitions;