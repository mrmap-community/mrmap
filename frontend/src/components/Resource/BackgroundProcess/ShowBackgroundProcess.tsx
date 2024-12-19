import { DateField, NumberField, RaRecord, ShowView, SimpleShowLayout, TextField } from 'react-admin';
import RealtimeShowContextProvider from '../../../jsonapi/components/Realtime/RealtimeShowContextProvider';
import ProgressField from '../../Field/ProgressField';

export const IS_STALE_CHECK_INTERVAL = 10

export const isStale = (timestamp: number, record: RaRecord) => {
  const stateTime = new Date(timestamp).getTime()
  const nowTime = new Date(Date.now()).getTime()
  console.log(record)
  if (record?.status === 'completed') return false;

  if (nowTime - stateTime > IS_STALE_CHECK_INTERVAL){
    return true
  }

  return false
}

const ShowBackgroundProcess = () => { 
    return (
      <RealtimeShowContextProvider
        isStaleCheckInterval={IS_STALE_CHECK_INTERVAL}
        isStale={isStale}
      >
        <ShowView>
        <SimpleShowLayout>
          <TextField source="status" />
          <TextField source="phase" />
          <DateField source="dateCreated" showTime/>
          <DateField source="doneAt" showTime/>
          <NumberField source="totalSteps"/>
          <NumberField source="doneSteps"/>
          <ProgressField source="progress"/>
        </SimpleShowLayout>
        </ShowView>
      </RealtimeShowContextProvider>
    )
};

export default ShowBackgroundProcess