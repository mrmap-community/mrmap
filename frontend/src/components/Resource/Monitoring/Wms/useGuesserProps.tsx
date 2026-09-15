import { useMemo } from 'react';
import { useRecordContext } from 'react-admin';
import { ReferenceManyInput } from '../../../../jsonapi/components/ReferenceManyInput';
import useWebMapServiceMonitoringSettingFieldDefinitions from './useWebMapServiceMonitoringSettingFieldDefinitions';


const useGuesserProps = () => {
  const record = useRecordContext()

  const fieldDefinitions = useWebMapServiceMonitoringSettingFieldDefinitions()
  const guesserProps = useMemo(()=> ({
    resource: "WebMapServiceMonitoringSetting",
    updateFieldDefinitions: fieldDefinitions,
    defaultValues:{
      service: record
    },
    referenceInputs: [
      <ReferenceManyInput 
        key='getCapabilititesProbes' 
        reference='GetCapabilitiesProbe' 
        source='getCapabilititesProbes'
        target='setting'
      />,
      <ReferenceManyInput
        key='getMapProbes' 
        reference='GetMapProbe'
        source='getMapProbes'
        target='setting'
      />
    ]            
  }),[
    fieldDefinitions
  ])
  return guesserProps
}

export default useGuesserProps;