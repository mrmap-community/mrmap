import { PropsWithChildren, useMemo } from 'react';
import { ListContextProvider, ResourceContextProvider, useGetList, useList, useResourceDefinition } from 'react-admin';
import { useHttpClientContext } from '../../../../context/HttpClientContext';

export interface HistoryBaseProps extends PropsWithChildren{
  resource?: string
  filter?: any
}

const HistoryListProvider = ({
  ...props
}: HistoryBaseProps) => {
  const { name } = useResourceDefinition({resource: props.resource})
  const { data, isPending, error } = useGetList(`Statistical${name}`, {sort: {field: "id", order: "DESC"}, filter: props.filter})
  const listContext = useList({ 
        data,
        isPending,
        error,
    });  

return (
  <ListContextProvider value={listContext}>
      {props.children}
  </ListContextProvider>
)
}

const HistoryListBase = (
  {
    ...props
  }: HistoryBaseProps
) => {
  const { name } = useResourceDefinition({resource: props.resource})

  const { api } = useHttpClientContext()
  const hasStatisticalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Statistical${name}`)),[api])

  if (!hasStatisticalEndpoint){
    return <></>
  }

  return (
    <ResourceContextProvider value={name}>
      <HistoryListProvider resource={name} { ...props}/>
    </ResourceContextProvider>
  )
}

export default HistoryListBase;