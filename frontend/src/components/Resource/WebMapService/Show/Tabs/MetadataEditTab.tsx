import { DeleteButton, SaveButton, Toolbar } from 'react-admin';
import EditGuesser from '../../../../../jsonapi/components/EditGuesser';



const MetadataEditTab = () => {

  return (
    <EditGuesser 
      resource='WebMapService'
      //id={settingId}
      redirect={false}
      actions={false}
      simpleFormProps={{
          toolbar:
          <Toolbar sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <SaveButton alwaysEnable/>
              <DeleteButton/>
          </Toolbar>
      
      }}
    />
  )
}


export default MetadataEditTab