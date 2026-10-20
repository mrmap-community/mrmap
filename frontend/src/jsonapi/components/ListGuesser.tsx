import { createElement, type ReactElement, type ReactNode, useEffect, useMemo, useState } from 'react'
import { useThemeProps } from '@mui/material/styles'
import { Box } from '@mui/material'
import { DatagridConfigurable, DatagridConfigurableProps, EditButton, List, ListBase, ListView, Loading, type ListProps, type RaRecord, ShowButton, useResourceDefinition, useSidebarState, useStore, WrapperField } from 'react-admin'
import { useParams } from 'react-router-dom'


import { merge } from 'lodash'
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
import RealtimeListBase from './Realtime/RealtimeListBase'
import { SelectedRecordContextProvider, useSelectedRecordContext } from './SelectedRecordContext'



export interface ListGuesserProps extends Partial<ListProps> {
  /** Rendered above the toolbar, inside the list context, including on empty lists. */
  header?: ReactNode
  listContent?: ReactElement
  /** Ordered fields for the existing grid; schema-generated fields are the default. */
  columns?: ReactElement[]
  additionalFilters?: FieldDefinition[]
  realtime?: boolean
  relatedResource?: Partial<RelatedResource>
  rowActions?: ReactNode
  additionalActions?: ReactNode
  onRowClick?: (clickedRecord: RaRecord) => void
  updateFieldDefinitions?: FieldDefinition[];
  refetchInterval?: number | false
  defaultSelectedColumns? : string[]
  ActionsComponent?: React.ComponentType<CustomListActionsProps>
  dataGridProps?: DatagridConfigurableProps
}

const defaultFilter = {}
const defaultLoading = <Loading />

const ListWithHeader = (props: ListProps & { header?: ReactNode; realtime?: boolean }) => {
  const {
    header,
    aside,
    realtime,
    debounce,
    disableAuthentication,
    disableSyncWithLocation,
    exporter,
    filter = defaultFilter,
    filterDefaultValues,
    authLoading = defaultLoading,
    loading,
    perPage = 10,
    queryOptions,
    resource,
    sort,
    storeKey,
    ...viewProps
  } = useThemeProps({ props, name: 'RaList' })
  const Base = realtime ? RealtimeListBase : ListBase

  return (
    <Base
      debounce={debounce}
      disableAuthentication={disableAuthentication}
      disableSyncWithLocation={disableSyncWithLocation}
      exporter={exporter}
      filter={filter}
      filterDefaultValues={filterDefaultValues}
      authLoading={authLoading}
      loading={realtime ? loading ?? defaultLoading : loading}
      perPage={perPage}
      queryOptions={queryOptions}
      resource={resource}
      sort={sort}
      storeKey={storeKey}
      offline={false}
    >
      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, alignItems: 'flex-start' }}>
        <Box sx={{ flex: '1 1 0', minWidth: 0, width: '100%' }}>
          {header}
          <ListView {...viewProps} />
        </Box>
        {aside}
      </Box>
    </Base>
  )
}



const ListGuesserContent = ({
  header,
  listContent,
  columns,
  additionalFilters,
  realtime=false,
  relatedResource = undefined,
  rowActions = undefined,
  additionalActions = undefined,
  onRowClick = undefined,
  updateFieldDefinitions,
  refetchInterval=false,
  defaultSelectedColumns = ["stringRepresentation", "title", "abstract", "username", "actions", "id"],
  ActionsComponent=ListActions,
  dataGridProps,
  ...props
}: ListGuesserProps): ReactElement => {
  const ListComponent = header != null ? ListWithHeader : realtime ? RealtimeList : List
  const { name, hasShow, options } = useResourceDefinition(props)
  const listOptions = useMemo(()=>(options?.list),[options])

  const { api } = useHttpClientContext()
  const [open] = useSidebarState()

  const { selectedRecord, setSelectedRecord } = useSelectedRecordContext()

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
  const filters = useMemo<ReactElement[]>(() => [
    ...(additionalFilters?.map(def => createElement(def.component, def.props)) ?? []),
    ...fieldSchemas
      .filter(def => !additionalFilters?.some(
        filterDef => filterDef.props.source === def.props.source
      ))
      .map(def => createElement(def.component, def.props))
  ], [fieldSchemas, additionalFilters])
  
  const hasHistoricalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Historical${name}`)),[api, name])

  const preferenceKey = useMemo(()=>(`${operationId}.datagrid`),[operationId])
  const gridPreferenceKey = columns ? `${preferenceKey}.customColumns` : preferenceKey
  const onError = useOnError(preferenceKey)
 
  const defaultOmit = useMemo(()=>fieldDefinitions.map(def => def.props.source).filter(source => !defaultSelectedColumns.includes(source)),[fieldDefinitions])
  const [initOmit, setInitOmit] = useState(false)
  const [_, setOmit] = useStore<string[]>(`preferences.${preferenceKey}.omit`)
  const jsonApiQuery = useJsonApiQuery( {relatedResource: relatedResource?.resource} )

  const queryOptions = useMemo(()=>(
    merge(
          {
            refetchInterval,
            onError,
            meta: (relatedResource?.resource !==  undefined)
              ? {
                relatedResource: {
                  resource: relatedResource?.resource,
                  id: relatedResource?.id ?? id
                },
                jsonApiParams: { ...jsonApiQuery }
              }
              : {
                jsonApiParams: { ...jsonApiQuery }
              }
          },
          props.queryOptions
        )
      ),[id, jsonApiQuery, relatedResource])


  useEffect(()=>{
    if(!columns && defaultOmit.length > 0 && !initOmit){
      setOmit(defaultOmit)
      setInitOmit(true)
    }
  },[defaultOmit, columns])


  if (operation === undefined || (columns ?? fields).length === 0) {
    // if fields are empty the table will be initial rendered only with the default index column.
    // when fields are filled after that render cyclus, the datagrid will be stuck with this single column
    // untill a new full render cyclus becomes started for the datagrid. (for example page change)
    return <div />
  }

  return (
    <ListComponent
      {...(header != null ? { header, realtime } : {})}
      filters={filters}
      storeKey={`preferences.${preferenceKey}.listParams`}
      actions={<ActionsComponent
        preferenceKey={gridPreferenceKey}
        />
      }
      empty={props.empty || <EmptyList />}
      queryOptions={queryOptions}
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
      filter={['WebMapService', 'WebFeatureService', 'Layer', 'FeatureType'].includes(name)
        ? { is_update_candidate: false, ...props.filter }
        : props.filter}
    >
      {listContent ?? <DatagridConfigurable
        
        bulkActionButtons={false}
        rowSx={record => record.id === selectedRecord?.id ? {
          backgroundColor: 'action.selected',
          '&:hover': { backgroundColor: 'action.selected' },
        } : {}}
        rowClick={(id, resource, record) => {
          onRowClick && onRowClick(record)
          if (selectedRecord !== record) {
            setSelectedRecord(record)
          }
          return false
        }}
        preferenceKey={gridPreferenceKey}
        omit={columns ? [] : defaultOmit}
        empty={<EmptyListWithFilter />}
        {...dataGridProps}
      >
        {columns ?? fields}
        {/**TODO: label should be translated */}
        {
          rowActions || <WrapperField label={"ra.list.actions"} >
            {hasShow && <ShowButton />}
            {<EditButton />}
            {additionalActions || listOptions?.additionalActions && createElement(listOptions?.additionalActions)}
          </WrapperField >
        }
      </DatagridConfigurable >}

    </ListComponent >
  )
}

const ListGuesser = (props: ListGuesserProps): ReactElement => (
  <SelectedRecordContextProvider>
    <ListGuesserContent {...props} />
  </SelectedRecordContextProvider>
)

export default ListGuesser
