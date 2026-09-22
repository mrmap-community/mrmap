import { useMemo } from 'react';
import { useRecordContext } from 'react-admin';
import useWebMapServiceMonitoringSettingFieldDefinitions from '../Monitoring/WebMapServiceMonitoringSetting/useWebMapServiceMonitoringSettingFieldDefinitions';


const useGuesserProps = () => {
  const record = useRecordContext()

  const fieldDefinitions = useWebMapServiceMonitoringSettingFieldDefinitions()
  const guesserProps = useMemo(()=> ({
    resource: "AllowedWebMapServiceOperation",
    updateFieldDefinitions: fieldDefinitions,
    defaultValues:{
      securedService: record
    }
  }),[
    fieldDefinitions
  ])
  return guesserProps
}

export default useGuesserProps;