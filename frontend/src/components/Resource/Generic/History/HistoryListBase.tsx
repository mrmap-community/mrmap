import { PropsWithChildren, useMemo } from 'react';
import { ListContextProvider, ResourceContextProvider, useGetList, useList, useResourceDefinition } from 'react-admin';
import { useHttpClientContext } from '../../../../context/HttpClientContext';

export interface HistoryBaseProps extends PropsWithChildren{
  resource?: string
  filter?: any
}

const HistoryListBase = (
  {
    resource,
    filter,
    ...props
  }: HistoryBaseProps
) => {
  const { name } = useResourceDefinition({resource: resource})

  const { api } = useHttpClientContext()
  const hasStatisticalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Statistical${name}`)),[api])

  if (!hasStatisticalEndpoint){
    return <></>
  }

  const { data, isPending, error } = useGetList(`Statistical${name}`, {sort: {field: "id", order: "DESC"}, filter: filter})
  const listContext = useList({ 
        data,
        isPending,
        error,
    });  

  return (
    <ResourceContextProvider value={name}>
      <ListContextProvider value={listContext}>
          {props.children}
      </ListContextProvider>
    </ResourceContextProvider>
  )
}

export default HistoryListBase;