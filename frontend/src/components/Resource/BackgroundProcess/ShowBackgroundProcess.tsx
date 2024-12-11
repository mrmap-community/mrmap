import { NumberField, SimpleShowLayout, TextField } from 'react-admin';
import RealtimeShow from '../../../jsonapi/components/Realtime/RealtimeShow';
import ProgressField from '../../Field/ProgressField';


const ShowBackgroundProcess = () => { 
    return (
      <RealtimeShow>
        <SimpleShowLayout>
          <TextField source="status" />
          <NumberField source="totalSteps"/>
          <NumberField source="doneSteps"/>
          <ProgressField source="progress"/>
        </SimpleShowLayout>
      </RealtimeShow>
    )
};

export default ShowBackgroundProcess