import { useMemo } from 'react';
import { useRecordContext } from 'react-admin';
import useWebMapServiceMonitoringUpdateFieldDefinitions from './useWebMapServiceUpdateSettingFieldDefinitions';



const useGuesserProps = () => {
  const record = useRecordContext()

  const fieldDefinitions = useWebMapServiceMonitoringUpdateFieldDefinitions()
  const guesserProps = useMemo(()=> ({
    resource: "WebMapServiceUpdateSetting",
    updateFieldDefinitions: fieldDefinitions,
    defaultValues:{
      service: record
    },
  }),[
    fieldDefinitions
  ])
  return guesserProps
}

export default useGuesserProps;