import { useMemo } from 'react';
import { useRecordContext, WrapperField } from 'react-admin';
import ListGuesser from '../../../jsonapi/components/ListGuesser';
import { ReferenceManyInput } from '../../../jsonapi/components/ReferenceManyInput';
import EditDialogButton from '../../Dialog/EditDialogButton';
import useWebMapServiceMonitoringSettingFieldDefinitions from '../Monitoring/Wms/useWebMapServiceMonitoringSettingFieldDefinitions';


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


const RowActions = () => {
  const guesserProps = useGuesserProps()
  return (
    <WrapperField label={"ra.list.actions"} >
        <EditDialogButton 
          guesserProps={guesserProps}
        />
    </WrapperField >
  )
}




export const MonitoringSettingsTab = () => {
  const guesserProps = useGuesserProps()
  return (
    <ListGuesser
      resource='WebMapServiceMonitoringSetting'
      relatedResource='WebMapService'
      dialogGuesserProps={{guesserProps}}

      //defaultSelectedColumns={["allowedArea", "description", "allowedGroups", "operations"]}
      
      rowActions={<RowActions/>}
     // {...props}
    />
  )
}

export default MonitoringSettingsTab