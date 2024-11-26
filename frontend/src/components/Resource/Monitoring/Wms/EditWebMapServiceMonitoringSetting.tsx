import { DeleteButton, SaveButton, Toolbar } from 'react-admin';
import { useParams } from 'react-router-dom';
import EditGuesser from '../../../../jsonapi/components/EditGuesser';
import { ReferenceManyInput } from '../../../../jsonapi/components/ReferenceManyInput';


const EditWebMapServiceMonitoringSetting = () => {
  
  // id of the WebMapServiceMonitoringSetting record
  const { id: settingId } = useParams()
  
  return (
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

export default EditWebMapServiceMonitoringSetting
