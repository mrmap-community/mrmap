import { createElement, type ReactElement, type ReactNode, useEffect, useMemo, useState } from 'react'
import { DatagridConfigurable, EditButton, List, type ListProps, type RaRecord, ShowButton, useResourceDefinition, useSidebarState, useStore, WrapperField } from 'react-admin'
import { useParams } from 'react-router-dom'


import HistoryList from '../../components/HistoryList'
import AsideCard from '../../components/Layout/AsideCard'
import ListActions, { CustomListActionsProps } from '../../components/Lists/CustomListActions'
import EmptyList from '../../components/Lists/Empty'
import EmptyListWithFilter from '../../components/Lists/EmptyWithFilter'
import { useHttpClientContext } from '../../context/HttpClientContext'
import { RelatedResource } from '../../providers/dataProvider'
import { useFieldsForOperation } from '../hooks/useFieldsForOperation'
import { useFilterInputForOperation } from '../hooks/useFilterInputForOperation'
import useJsonApiQuery from '../hooks/useJsonApiQuery'
import useOnError from '../hooks/useOnError'
import useResourceSchema from '../hooks/useResourceSchema'
import { FieldDefinition } from '../utils'
import RealtimeList from './Realtime/RealtimeList'



export interface ListGuesserProps extends Partial<ListProps> {
  realtime?: boolean
  relatedResource?: Partial<RelatedResource>
  rowActions?: ReactNode
  additionalActions?: ReactNode
  onRowClick?: (clickedRecord: RaRecord) => void
  updateFieldDefinitions?: FieldDefinition[];
  refetchInterval?: number | false
  defaultSelectedColumns? : string[]
  ActionsComponent?: React.ComponentType<CustomListActionsProps>
}



const ListGuesser = ({
  realtime=false,
  relatedResource = undefined,
  rowActions = undefined,
  additionalActions = undefined,
  onRowClick = undefined,
  updateFieldDefinitions,
  refetchInterval=false,
  defaultSelectedColumns = ["stringRepresentation", "title", "abstract", "username", "actions", "id"],
  ActionsComponent=ListActions,
  ...props
}: ListGuesserProps): ReactElement => {
  const ListComponent = realtime ? RealtimeList: List
  const { name, hasShow, options } = useResourceDefinition(props)
  const listOptions = useMemo(()=>(options.list),[options])

  const { api } = useHttpClientContext()
  const [open] = useSidebarState()

  const [selectedRecord, setSelectedRecord] = useState<RaRecord>()

  const { id } = useParams()
  const operationId = useMemo(()=> relatedResource !== undefined && relatedResource?.resource !== '' ?`list_related_${name}_of_${relatedResource?.resource}`: `list_${name}`, [relatedResource?.resource, name])
  const { operation } = useResourceSchema(operationId)
  const fieldDefinitions = useFieldsForOperation({operationId: operationId, forInput:false, ignoreId:false})
  const fields = useMemo(
    () => fieldDefinitions.map(fieldDefinition => {
      const update = updateFieldDefinitions?.find(def => def.props.source === fieldDefinition.props.source)
      return createElement(
        update?.component || fieldDefinition.component, 
        {
          ...fieldDefinition.props,
          key: `${fieldDefinition.props.source}`,
          ...update?.props
        }
      )
    })
  ,[fieldDefinitions])
  
  const fieldSchemas = useFilterInputForOperation(operationId)
  const filters = useMemo(() => fieldSchemas.map(def => createElement(def.component, def.props)), [fieldSchemas])
  
  const hasHistoricalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Historical${name}`)),[api, name])

  const preferenceKey = useMemo(()=>(`${operationId}.datagrid`),[operationId])
  const onError = useOnError(preferenceKey)
 
  const defaultOmit = useMemo(()=>fieldDefinitions.map(def => def.props.source).filter(source => !defaultSelectedColumns.includes(source)),[fieldDefinitions])
  const [initOmit, setInitOmit] = useState(false)
  const [_, setOmit] = useStore<string[]>(`preferences.${preferenceKey}.omit`)
  
  useEffect(()=>{
    if(defaultOmit.length > 0 && !initOmit){
      setOmit(defaultOmit)
      setInitOmit(true)
    }
  },[defaultOmit])


  const jsonApiQuery = useJsonApiQuery( {relatedResource: relatedResource ? relatedResource.resource: undefined})

  if (operation === undefined || fields === undefined || fields?.length === 0) {
    // if fields are empty the table will be initial rendered only with the default index column.
    // when fields are filled after that render cyclus, the datagrid will be stuck with this single column
    // untill a new full render cyclus becomes started for the datagrid. (for example page change)
    return <div />
  }

  return (
    <ListComponent
      filters={filters}
      storeKey={`preferences.${preferenceKey}.listParams`}
      actions={<ActionsComponent
        filters={filters} 
        preferenceKey={preferenceKey}
        />
      }
      empty={props.empty || <EmptyList />}
      queryOptions={{
        refetchInterval,
        onError,
        meta: (relatedResource?.resource !== '')
          ? {
            jsonApiParams: { ...jsonApiQuery }
          }
          : {
            relatedResource: {
              resource: relatedResource?.resource,
              id: relatedResource?.id ?? id
            },
            jsonApiParams: { ...jsonApiQuery }
          }
      }}
      

      aside={
        hasHistoricalEndpoint ?
        <AsideCard
          sx={{
            margin: '1em',
            //height: 'calc(100vh - 110px - 1em)', // 174px ==> 50 appbar, 52 pagination,  1 em top padding
            width: `calc(${open ? '40vw' : '20vw'} - 1em - ${open ? '240px' : '50px'})`,
            overflowY: 'scroll'
          }}
        >
          <HistoryList
            resource={`Historical${name ?? ''}`}
            related={name ?? ''}
            record={selectedRecord}
           
          />
        </AsideCard>: undefined
      }
      {...props}
    >
      <DatagridConfigurable
        bulkActionButtons={false}
        rowClick={(id, resource, record) => {
          onRowClick && onRowClick(record)
          if (selectedRecord !== record) {
            setSelectedRecord(record)
          }
          return false
        }}
        preferenceKey={preferenceKey}
        omit={defaultOmit}
        empty={<EmptyListWithFilter />}
      >
        {...fields}
        {/**TODO: label should be translated */}
        {
          rowActions || <WrapperField label={"ra.list.actions"} >
            {hasShow && <ShowButton />}
            {<EditButton />}
            {additionalActions || listOptions?.additionalActions && createElement(listOptions?.additionalActions)}
          </WrapperField >
        }
      </DatagridConfigurable >

    </ListComponent >
  )
}

export default ListGuesser
