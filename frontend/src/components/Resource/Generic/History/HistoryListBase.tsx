import { Fragment, PropsWithChildren, ReactNode, useMemo } from 'react';
import { ListContextProvider, ResourceContextProvider, useGetList, useList, useResourceDefinition } from 'react-admin';

import { useHttpClientContext } from '../../../../context/HttpClientContext';

export interface HistoryBaseProps extends PropsWithChildren{
  resource?: string
  filter?: import("react-admin").FilterPayload
  fallback?: ReactNode
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

/**
 * The days of the changes of a resource, which what is built on them asks.
 *
 * The statistics of a resource are answered by the api per day and only for the
 * days which did have a change, so whatever is built on them has to ask the api
 * itself and must not count the records of a page.
 */
const HistoryListBase = (
  {
    /** what to answer when the resource answers no statistics at all, which is
     *  another answer than statistics which answer no change */
    fallback = <Fragment></Fragment>,
    ...props
  }: HistoryBaseProps
) => {
  const { name } = useResourceDefinition({resource: props.resource})

  const { api } = useHttpClientContext()
  const hasStatisticalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Statistical${name}`)),[api])

  if (!hasStatisticalEndpoint){
    return fallback
  }

  return (
    <ResourceContextProvider value={name}>
      <HistoryListProvider resource={name} { ...props}/>
    </ResourceContextProvider>
  )
}

export default HistoryListBase;