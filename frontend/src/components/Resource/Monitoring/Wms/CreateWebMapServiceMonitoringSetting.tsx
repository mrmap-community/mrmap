import { useCallback } from 'react';
import { DeleteButton, Identifier, RaRecord, SaveButton, Toolbar } from 'react-admin';
import { useParams } from 'react-router-dom';
import CreateGuesser from '../../../../jsonapi/components/CreateGuesser';
import EditGuesser from '../../../../jsonapi/components/EditGuesser';
import { ReferenceManyInput } from '../../../../jsonapi/components/ReferenceManyInput';


const CreateWebMapServiceMonitoringSetting = () => {
  
  // id of the WebMapServiceMonitoringSetting record
  const { id: settingId } = useParams()

  // TODO: set the state for nested forms ==> GetCapabilititesProbes & GetMapProbes
  const redirect = useCallback((
      resource?: string,
      id?: Identifier,
      data?: Partial<RaRecord>,
      state?: object
    ) => `WebMapServiceMonitoringSetting/${id}`  
  , [settingId])
  
  return (
    settingId === undefined ? 
    <CreateGuesser
      resource='WebMapServiceMonitoringSetting'
      redirect={redirect}
    />: 
    <EditGuesser 
      resource='WebMapServiceMonitoringSetting'
      id={settingId}
      redirect={false}      
      toolbar={
        <Toolbar sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <SaveButton alwaysEnable/>
            <DeleteButton/>
        </Toolbar>
      }
      referenceInputs={[
        <ReferenceManyInput key='getCapabilitiesProbes' reference='GetCapabilitiesProbe' target='setting'/>,
        <ReferenceManyInput key='getMapProbes' reference='GetMapProbe' target='setting'/>
      ]}
    />
  )
}

export default CreateWebMapServiceMonitoringSetting
