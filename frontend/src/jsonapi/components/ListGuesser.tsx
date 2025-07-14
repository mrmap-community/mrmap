import { createElement, type ReactElement, type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { type ConfigurableDatagridColumn, DatagridConfigurable, EditButton, ExportButton, FilterButton, Identifier, List, type ListProps, type RaRecord, SelectColumnsButton, ShowButton, TopToolbar, useResourceDefinition, useSidebarState, useStore } from 'react-admin'
import { useParams, useSearchParams } from 'react-router-dom'

import axios from 'axios'
import { snakeCase } from 'lodash'

import CreateDialogButton from '../../components/Dialog/CreateDialogButton'
import HistoryList from '../../components/HistoryList'
import AsideCard from '../../components/Layout/AsideCard'
import EmptyList from '../../components/Lists/Empty'
import { useHttpClientContext } from '../../context/HttpClientContext'
import { useFieldsForOperation } from '../hooks/useFieldsForOperation'
import { useFilterInputForOperation } from '../hooks/useFilterInputForOperation'
import useResourceSchema from '../hooks/useResourceSchema'
import { type JsonApiDocument, type JsonApiErrorObject, SparseFieldsets } from '../types/jsonapi'
import { FieldDefinition, getIncludeOptions, getSparseFieldOptions } from '../utils'
import RealtimeList from './Realtime/RealtimeList'

interface FieldWrapperProps {
  children: ReactNode[]
  label: string
}

interface ListActionsProps {
  filters: ReactNode[]
  preferenceKey?: string
}

interface ListGuesserProps extends Partial<ListProps> {
  realtime?: boolean
  relatedResource?: string
  relatedResourceId?: Identifier
  rowActions?: ReactNode
  additionalActions?: ReactNode
  onRowClick?: (clickedRecord: RaRecord) => void
  updateFieldDefinitions?: FieldDefinition[];
  refetchInterval?: number | false
  defaultSelectedColumns? : string[]
  sparseFieldsets?: SparseFieldsets[]
}


const FieldWrapper = ({ children }: FieldWrapperProps): ReactNode => children

const isInvalidSort = (error: JsonApiErrorObject): boolean => {
  if (error.code === 'invalid' && error.detail.includes('sort parameter')) {
    return true
  }
  return false
}

const isInvalidFilter = (error: JsonApiErrorObject): boolean => {
  if (error.code === 'invalid' && error.detail.includes('invalid filter')) {
    return true
  }
  return false
}


const ListActions = (
  { 
    filters,
    preferenceKey,
  }: ListActionsProps
): ReactNode => {
  const { hasCreate} = useResourceDefinition()
  return (
    <TopToolbar>
      <SelectColumnsButton preferenceKey={preferenceKey}/>
      <FilterButton filters={filters}/>
      {hasCreate && <CreateDialogButton />}
      <ExportButton />
    </TopToolbar>
  )
}

const ListGuesser = ({
  realtime=false,
  relatedResource = '',
  relatedResourceId = undefined,
  rowActions = undefined,
  additionalActions = undefined,
  onRowClick = undefined,
  updateFieldDefinitions,
  refetchInterval=false,
  defaultSelectedColumns = ["stringRepresentation", "title", "abstract", "username", "actions", "id"],
  sparseFieldsets= undefined,
  ...props
}: ListGuesserProps): ReactElement => {

  const ListComponent = realtime ? RealtimeList: List
  const { name, hasShow, hasEdit } = useResourceDefinition(props)
  const { api } = useHttpClientContext()
  const [open] = useSidebarState()

  const [selectedRecord, setSelectedRecord] = useState<RaRecord>()

  const { id } = useParams()
  const operationId = useMemo(()=> relatedResource !== undefined && relatedResource !== '' ?`list_related_${name}_of_${relatedResource}`: `list_${name}`, [relatedResource, name])
  const { operation } = useResourceSchema(operationId)
  const fieldDefinitions = useFieldsForOperation(operationId, false, false)
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
  
  const includeOptions = useMemo(() => (operation !== undefined) ? getIncludeOptions(operation) : [], [operation])
  const sparseFieldOptions = useMemo(() => (operation !== undefined) ? getSparseFieldOptions(operation) : [], [operation])

  const hasHistoricalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Historical${name}`)),[api, name])

  const preferenceKey = useMemo(()=>(`${operationId}.datagrid`),[operationId])

  const [searchParams, setSearchParams] = useSearchParams()

  const [listParams, setListParams] = useStore(`preferences.${preferenceKey}.listParams`, {})

  const defaultOmit = useMemo(()=>fieldDefinitions.map(def => def.props.source).filter(source => !defaultSelectedColumns.includes(source)),[fieldDefinitions])
  const [initOmit, setInitOmit] = useState(false)
  const [availableColumns] = useStore<ConfigurableDatagridColumn[]>(`preferences.${preferenceKey}.availableColumns`, [])
  const [omit, setOmit] = useStore<string[]>(`preferences.${preferenceKey}.omit`)
  const [selectedColumnsIdxs] = useStore<string[]>(`preferences.${preferenceKey}.columns`, [])
  
  useEffect(()=>{
    if(defaultOmit.length > 0 && !initOmit){
      setOmit(defaultOmit)
      setInitOmit(true)
    }
  },[defaultOmit])


  const sparseFieldsQueryValue = useMemo(
    () => availableColumns.filter(column => {
      if (column.source === undefined) return false
      
      return sparseFieldOptions.includes(column.source) &&
      selectedColumnsIdxs.length > 0 ? selectedColumnsIdxs.includes(column.index): !(omit || []).includes(column.source)
     }
      ).map(column =>
      // TODO: django jsonapi has an open issue where no snake to cammel case translation are made
      // See https://github.com/django-json-api/django-rest-framework-json-api/issues/1053
      snakeCase(column.source)
    ), [sparseFieldOptions, availableColumns, selectedColumnsIdxs])

  const includeQueryValue = useMemo(
    () => includeOptions.filter(includeOption => sparseFieldsQueryValue.includes(includeOption)), 
    [sparseFieldsQueryValue, includeOptions])

  const jsonApiQuery = useMemo(
    () => {
      const query: any = {}

      if (sparseFieldsets !== undefined) {
        sparseFieldsets.forEach(sf => {
          if (name === sf.type){

            const fields = [...new Set([
              ...sf.fields.map(value =>
                // TODO: django jsonapi has an open issue where no snake to cammel case translation are made
                // See https://github.com/django-json-api/django-rest-framework-json-api/issues/1053
                snakeCase(value)), 
              ...sparseFieldsQueryValue || []
            ])]
            query[`fields[${sf.type}]`] = fields.join(',')
          } else {
            query[`fields[${sf.type}]`] = sf.fields.join(',')
          }
        })
      }

      if (sparseFieldsets === undefined && sparseFieldsQueryValue !== undefined) {
        query[`fields[${name}]`] = sparseFieldsQueryValue.join(',')
      }

      if (includeQueryValue !== undefined) {
        query.include = includeQueryValue.join(',')
      }

      return query
    }
    , [sparseFieldsets, sparseFieldsQueryValue, includeQueryValue]
  )

  const onError = useCallback((error: Error): void => {
    /** Custom error handler for jsonApi bad request response
     *
     * possible if:
     *   - attribute is not sortable
     *   - attribute is not filterable
     *   - wrong sparseField
     *   - wrong include option
     *
    */
    if (axios.isAxiosError(error)) {
      if (error?.status === 400) {
        const jsonApiDocument = error.response?.data as JsonApiDocument

        jsonApiDocument?.errors?.forEach((apiError: JsonApiErrorObject) => {
          if (isInvalidSort(apiError)) {
            // remove sort from storage
            setListParams({...listParams, sort: ''})

            // remove sort from current location
            searchParams.delete('sort')
            setSearchParams(searchParams)
          }
          if (isInvalidFilter(apiError)){
            setListParams({...listParams, filter: ''})
            
            searchParams.delete('filter')
            setSearchParams(searchParams)
          }
        })
      } else if (error.status === 401) {
        // TODO
      } else if (error.status === 403) {
        // TODO
      }
    }
  }, [])

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
      actions={<ListActions filters={filters} preferenceKey={preferenceKey}/>}
      empty={props.empty || <EmptyList />}
      queryOptions={{
        refetchInterval,
        onError,
        meta: (relatedResource !== undefined && relatedResource !== '')
          ? {
            relatedResource: {
              resource: relatedResource,
              id: relatedResourceId ?? id
            },
            jsonApiParams: { ...jsonApiQuery }
          }
          : {
            jsonApiParams: { ...jsonApiQuery }
          }
      }}
      
      sx={
        {
          '& .RaList-main': {
            width: `calc(${open ? '60vw' : '80vw'} - ${open ? '240px' : '50px - 2em'})`,
            //maxHeight: 'calc(50vh - 174px )', // 174px ==> 50 appbar, 52 pagination, 64 table actions, 8 top padding
            overfloxX: 'hidden',
            marginLeft: "1em",
            marginRight: "1em",
            marginBottom: "1em",
          },
          '& .RaDatagrid-tableWrapper': {
            overflowX: 'scroll',
            margin: "1em",
          }
        }
      }

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
      >
        {...fields}
        {/**TODO: label should be translated */}
        {
          rowActions || <FieldWrapper label="Actions" >
              {hasShow && <ShowButton />}
              {hasEdit && <EditButton />}
              {additionalActions}
            </FieldWrapper >
        }
      </DatagridConfigurable >

    </ListComponent >
  )
}

export default ListGuesser
