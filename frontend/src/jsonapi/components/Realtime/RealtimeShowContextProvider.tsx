import { PropsWithChildren, useCallback, useEffect, useState } from 'react';
import { RaRecord, ShowContextProvider, ShowControllerProps, useDataProvider, useResourceContext, useShowController } from 'react-admin';
import { CrudEvent } from '../../../providers/dataProvider';


export interface RealtimeShowProps extends ShowControllerProps, PropsWithChildren {
  isStaleCheckInterval?: number;
  isStale?: (timestamp: number, record: RaRecord) => boolean;
}


const RealtimeShowContextProvider = ({ 
  children,
  isStaleCheckInterval,
  isStale,
  ...rest
 }: RealtimeShowProps) => {
  const resource = useResourceContext(rest);
  if (!resource) {
      throw new Error(
          `RealtimeShow requires a non-empty resource prop or context`
      );
  }
  const dataProvider = useDataProvider()
  const { record, refetch, ...controllerProps } = useShowController({resource, ...rest});
  
  const [realtimeRecord, setRealtimeRecord] = useState<RaRecord | undefined>(record)
  const [timestamp, setTimestamp] = useState<number>(Date.now())

  const updateFromRealtimeBus = useCallback((message: CrudEvent) => {
    setRealtimeRecord(message?.payload?.records?.[0])
    setTimestamp(Date.now())
  }, [record])

  useEffect(() => {
    // subscribe on mount
    dataProvider.subscribe(`resource/${resource}/${record?.id}`, updateFromRealtimeBus)
    
    const interval = isStaleCheckInterval && setInterval(()=>{
      isStale && isStale(timestamp, record) && refetch()     
    }, isStaleCheckInterval * 1000);

    return () => {
      // unsubscribe on unmount
      dataProvider.unsubscribe(`resource/${resource}/${record?.id}`, updateFromRealtimeBus)

      // clear interval on unmount
      clearInterval(interval)
    }
  }, [resource, timestamp, record])

  useEffect(()=>{
    setRealtimeRecord(record)
  },[record])

  return (
      <ShowContextProvider value={{record: realtimeRecord || record, ...controllerProps}}>
          {children}
      </ShowContextProvider>
  )
}

export default RealtimeShowContextProvider