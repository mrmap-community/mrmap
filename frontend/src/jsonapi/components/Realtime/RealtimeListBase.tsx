import { useCallback, useEffect, useState } from "react";
import { ListBaseProps, ListContextProvider, OptionalResourceContextProvider, RaRecord, useDataProvider, useIsAuthPending, useListController } from "react-admin";
import { CrudEvent, Subscription } from "../../../providers/dataProvider";



const RealtimeListBase = <RecordType extends RaRecord = any>({
  children,
  loading = null,
  resource,
  ...props
}: ListBaseProps<RecordType>) => {
  const {data, ...controllerProps} = useListController<RecordType>({resource, ...props});

  const [realtimeData, setRealtimeData] = useState<RaRecord[]>(data || []);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);

  const dataProvider = useDataProvider();

  const isAuthPending = useIsAuthPending({
    resource: controllerProps.resource,
    action: 'list',
  });
  
  const handleBusEvent = useCallback((event: CrudEvent) => {
    
    if (event.type === "updated"){
      event.payload.ids.forEach(id => {
        const index = realtimeData?.findIndex(record => String(record.id) === String(id))
        const updatedRecord = event.payload.records?.find(record => String(record.id) === String(id))
        if (updatedRecord !== undefined && index && index > -1 ) {
          const newRealtimeData = [...realtimeData]
          const newRecordData = event.payload.records?.find(record => String(record.id) === String(id))
          if (newRecordData !== undefined){
            newRealtimeData[index] = newRecordData
          } 
          setRealtimeData(newRealtimeData)
        }
      })
    }
    
  }, [realtimeData])

  useEffect(()=>{
    setRealtimeData([])
  },[controllerProps.page])

  useEffect(()=>{
    setRealtimeData(data)

    // data is always the current page data
    const newSubscriptions = data?.map((record): Subscription  => ({
        topic: `resource/${resource}/${record.id}`,
        callback: handleBusEvent
      }
    )) || []

    // unsubscribe every unmounted record column
    subscriptions.filter(record => !newSubscriptions.some(r => r.topic === record.topic)).forEach(subscription => {
      dataProvider.unsubscribe(subscription.topic, subscription.callback)
    })
    
    setSubscriptions(newSubscriptions)
    
  }, [data])

  useEffect(()=>{
    // push subscriptions to dataprovider
    subscriptions.forEach(subscription => dataProvider.subscribe(subscription.topic, subscription.callback))
  }, [subscriptions])

  // useEffect(() => {
  //   // subscribe on mount
  //   resource && dataProvider.subscribe(`resource/${resource}`, handleBusEvent)
  //   // unsubscribe on unmount
  //   return () => resource && dataProvider.unsubscribe(`resource/${resource}`, handleBusEvent)
  // }, [dataProvider, handleBusEvent])

  if (isAuthPending && !props.disableAuthentication) {
    return loading;
  }

  return (
    // We pass props.resource here as we don't need to create a new ResourceContext if the props is not provided
    <OptionalResourceContextProvider value={resource}>
      <ListContextProvider value={{data: realtimeData, ...controllerProps}}>
          {children}
      </ListContextProvider>
    </OptionalResourceContextProvider>
  )

}

export default RealtimeListBase