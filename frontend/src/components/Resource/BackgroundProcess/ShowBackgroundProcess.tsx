import { DateField, FunctionField, NumberField, RaRecord, ShowView, SimpleShowLayout, TextField, useTranslate } from 'react-admin';

import RealtimeShowContextProvider from '../../../jsonapi/components/Realtime/RealtimeShowContextProvider';
import DurationField from '../../Field/DurationField';
import ProgressField from '../../Field/ProgressField';
import RelatedResourceField from '../../Field/RelatedResourceField';
import BackgroundProcessLogs from './BackgroundProcessLogs';
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
    const translate = useTranslate();
    return (
      <RealtimeShowContextProvider
        isStaleCheckInterval={IS_STALE_CHECK_INTERVAL_SECONDS}
        isStale={isStale}
      >
        <ShowView>
        <SimpleShowLayout>
          <ProcessStatusField source="status" />
          <RelatedResourceField source="relatedResource" />
          <TextField source="description" />
          {/* the phase is a key reported by the api, looked up in the
              background activity translations; a process which reported its
              error text instead answers that text raw (#1267) */}
          <FunctionField
            source="phase"
            render={(record: RaRecord) =>
              typeof record?.phase === "string" && record.phase !== ""
                ? translate(`backgroundActivity.phases.${record.phase}`, {
                    _: record.phase,
                  })
                : undefined
            }
          />
          <DateField source="dateCreated" showTime/>
          <DateField source="doneAt" showTime/>
          <DurationField source="duration" />
          <NumberField source="totalSteps"/>
          <NumberField source="doneSteps"/>
          <ProgressField source="progress"/>
        </SimpleShowLayout>
        {/* the errors the worker wrote survive the notification which announced
            them: they are read from the api of the process, not from a bus
            message which is gone on reload (#1208) */}
        <BackgroundProcessLogs />
        </ShowView>
      </RealtimeShowContextProvider>
    )
};

export default ShowBackgroundProcess