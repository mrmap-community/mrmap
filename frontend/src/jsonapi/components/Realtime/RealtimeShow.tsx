import { PropsWithChildren, useCallback, useEffect, useState } from 'react';
import { RaRecord, ShowContextProvider, ShowControllerProps, ShowView, useDataProvider, useResourceContext, useShowController } from 'react-admin';
import { CrudEvent } from '../../../providers/dataProvider';


export interface RealtimeShowProps extends ShowControllerProps, PropsWithChildren {
  
}


const RealtimeShow = ({ 
  children,
  ...rest
 }: RealtimeShowProps) => {
  const resource = useResourceContext(rest);
  if (!resource) {
      throw new Error(
          `RealtimeShow requires a non-empty resource prop or context`
      );
  }

  const dataProvider = useDataProvider()
  const { record, ...controllerProps } = useShowController({resource, ...rest});

  const [realtimeRecord, setRealtimeRecord] = useState<RaRecord | undefined>(record)
  const updateFromRealtimeBus = useCallback((message: CrudEvent) => {
    setRealtimeRecord(message?.payload?.records?.[0])
  }, [record])

  useEffect(() => {
    // subscribe on mount
    dataProvider.subscribe(`resource/${resource}/${record?.id}`, updateFromRealtimeBus)
    // unsubscribe on unmount
    return () => dataProvider.unsubscribe(`resource/${resource}/${record?.id}`, updateFromRealtimeBus)
  }, [dataProvider, updateFromRealtimeBus])

  return (
      <ShowContextProvider value={{record: realtimeRecord || record, ...controllerProps}}>
        <ShowView {...rest}>
          {children}
        </ShowView>
      </ShowContextProvider>
  )
}

export default RealtimeShow