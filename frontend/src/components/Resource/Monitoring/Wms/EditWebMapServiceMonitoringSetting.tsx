import { DeleteButton, SaveButton, Toolbar } from 'react-admin';
import { useParams } from 'react-router-dom';
import EditGuesser from '../../../../jsonapi/components/EditGuesser';
import { ReferenceManyInput } from '../../../../jsonapi/components/ReferenceManyInput';
import SchemaAutocompleteInput from '../../../../jsonapi/components/SchemaAutocompleteInput';
import CronInput from '../../../Input/CronInput';


const EditWebMapServiceMonitoringSetting = () => {
  
  // id of the WebMapServiceMonitoringSetting record
  const { id: settingId } = useParams()
  

  return (
    <EditGuesser 
      resource='WebMapServiceMonitoringSetting'
     // id={settingId}
      redirect={false}      
      simpleFormProps={{toolbar:
        <Toolbar sx={{ display: 'flex', justifyContent: 'space-between' }}>
          <SaveButton alwaysEnable={true}/>
          <DeleteButton/>
        </Toolbar>}
      }
      updateFieldDefinitions={
        [
          {
            component: CronInput, 
            props: {source: "scheduleInterval"}
          },
          {
            component: SchemaAutocompleteInput, 
            props: {source: "service", hidden: true}
          },
        ]
      }
      referenceInputs={[
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
      ]}
    />
  )
}

export default EditWebMapServiceMonitoringSetting
