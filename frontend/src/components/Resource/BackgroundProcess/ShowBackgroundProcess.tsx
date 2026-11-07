import { DateField, NumberField, RaRecord, ShowView, SimpleShowLayout, TextField } from 'react-admin';

import RealtimeShowContextProvider from '../../../jsonapi/components/Realtime/RealtimeShowContextProvider';
import ProgressField from '../../Field/ProgressField';
import RelatedResourceField from '../../Field/RelatedResourceField';
import ProcessStatusField from './ProcessStatusField';

/** how often the show screen looks whether the record it shows went stale,
 *  in seconds - the prop of the provider, which turns it into its tick */
export const IS_STALE_CHECK_INTERVAL_SECONDS = 10

/** how old the last moment the record was pushed over the bus may be before
 *  the screen throws the push away and refetches, in milliseconds: one check
 *  interval, so a record which was pushed within the interval stands and the
 *  screen never refetches on the tick it just answered (#1086) */
export const STALE_AFTER_MILLISECONDS = IS_STALE_CHECK_INTERVAL_SECONDS * 1000

export const isStale = (timestamp: number, record: RaRecord) => {
  const stateTime = new Date(timestamp).getTime()
  const nowTime = new Date(Date.now()).getTime()
  if (['completed', 'failed', 'aborted'].includes(record?.status)) return false;

  if (nowTime - stateTime > STALE_AFTER_MILLISECONDS){
    return true
  }

  return false
}

const ShowBackgroundProcess = () => { 
    return (
      <RealtimeShowContextProvider
        isStaleCheckInterval={IS_STALE_CHECK_INTERVAL_SECONDS}
        isStale={isStale}
      >
        <ShowView>
        <SimpleShowLayout>
          <ProcessStatusField source="status" />
          <RelatedResourceField source="relatedResource" />
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