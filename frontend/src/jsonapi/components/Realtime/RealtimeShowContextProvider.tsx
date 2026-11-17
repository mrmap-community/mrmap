import { PropsWithChildren, useCallback, useEffect, useRef, useState } from 'react';
import { RaRecord, ShowContextProvider, ShowControllerProps, useDataProvider, useResourceContext, useShowController } from 'react-admin';

import { CrudEvent } from '../../../providers/dataProvider';


export interface RealtimeShowContextProviderProps extends ShowControllerProps, PropsWithChildren {
  /** how often the provider asks its `isStale` whether the record went stale,
   *  in seconds - the threshold which `isStale` compares an age against is in
   *  milliseconds, so a consumer which names both must name them apart (#1086) */
  isStaleCheckInterval?: number;
  isStale?: (timestamp: number, record: RaRecord) => boolean;
}


const RealtimeShowContextProvider = ({ 
  children,
  isStaleCheckInterval,
  isStale,
  ...rest
 }: RealtimeShowContextProviderProps) => {
  const resource = useResourceContext(rest);
  if (!resource) {
      throw new Error(
          `RealtimeShow requires a non-empty resource prop or context`
      );
  }
  const dataProvider = useDataProvider()
  const controller = useShowController({resource, ...rest});
  const { record, refetch, isFetching } = controller;

  const [realtimeRecord, setRealtimeRecord] = useState<RaRecord | undefined>(record)

  // the freshness timestamp is mirrored in a ref (the pattern documented in
  // BackgroundJobCenterContext.tsx): the stale check reads it, the
  // subscription never does - keeping it out of the state means a bus event
  // neither rebuilds the subscription nor the interval anymore (#1462)
  const timestamp = useRef<number>(Date.now())

  const updateFromRealtimeBus = useCallback((message: CrudEvent) => {
    setRealtimeRecord(message?.payload?.records?.[0])
    timestamp.current = Date.now()
  }, [])

  // the values the stale check reads when it ticks, mirrored in a ref so
  // that the interval is built once per configured distance and not on every
  // render or event (#1462)
  const staleCheckState = useRef({ record, isFetching, isStale, refetch })
  useEffect(() => {
    staleCheckState.current = { record, isFetching, isStale, refetch }
  })

  useEffect(() => {
    // subscribe on mount
    dataProvider.subscribe(`resource/${resource}/${record?.id}`, updateFromRealtimeBus)

    return () => {
      // unsubscribe on unmount
      dataProvider.unsubscribe(`resource/${resource}/${record?.id}`, updateFromRealtimeBus)
    }
  }, [dataProvider, resource, record?.id, updateFromRealtimeBus])

  useEffect(() => {
    if (!isStaleCheckInterval) return
    const interval = setInterval(()=>{
      const { record, isFetching, isStale, refetch } = staleCheckState.current
      if (!isFetching && isStale?.(timestamp.current, record)) refetch()
    }, isStaleCheckInterval * 1000)

    return () => clearInterval(interval)
  }, [isStaleCheckInterval])

  useEffect(()=>{
    setRealtimeRecord(record)
  },[record])

  return (
      <ShowContextProvider value={controller.isPending ? controller : { ...controller, record: realtimeRecord || record }}>
          {children}
      </ShowContextProvider>
  )
}

export default RealtimeShowContextProvider
