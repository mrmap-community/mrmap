import { createElement, type ReactElement, type ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import { type ConfigurableDatagridColumn, CreateButton, DatagridConfigurable, EditButton, ExportButton, FilterButton, List, type ListProps, type RaRecord, SelectColumnsButton, ShowButton, TopToolbar, useResourceDefinition, useSidebarState, useStore } from 'react-admin'
import { useParams, useSearchParams } from 'react-router-dom'

import axios from 'axios'
import { snakeCase } from 'lodash'

import HistoryList from '../../components/HistoryList'
import { useHttpClientContext } from '../../context/HttpClientContext'
import { useFieldsForOperation } from '../hooks/useFieldsForOperation'
import { useFilterInputForOperation } from '../hooks/useFilterInputForOperation'
import useResourceSchema from '../hooks/useResourceSchema'
import { type JsonApiDocument, type JsonApiErrorObject } from '../types/jsonapi'
import { getIncludeOptions, getSparseFieldOptions } from '../utils'

interface FieldWrapperProps {
  children: ReactNode[]
  label: string
}

interface ListActionsProps {
  filters: ReactNode[]
}

interface ListGuesserProps extends Partial<ListProps> {
  relatedResource?: string
  rowActions?: ReactNode
  additionalActions?: ReactNode
  defaultOmit?: string[]
  onRowClick?: (clickedRecord: RaRecord) => void
  
}


const FieldWrapper = ({ children }: FieldWrapperProps): ReactNode => children

const isInvalidSort = (error: JsonApiErrorObject): boolean => {
  if (error.code === 'invalid' && error.detail.includes('sort parameter')) {
    return true
  }
  return false
}

const ListActions = (
  { filters }: ListActionsProps
): ReactNode => {
  const { hasCreate} = useResourceDefinition()
  return (
    <TopToolbar>
      <SelectColumnsButton />
      <FilterButton filters={filters} />
      {hasCreate && <CreateButton />}
      <ExportButton />
    </TopToolbar>
  )
}

const ListGuesser = ({
  relatedResource = '',
  rowActions = undefined,
  additionalActions = undefined,
  onRowClick = undefined,
  defaultOmit = [],
  ...props
}: ListGuesserProps): ReactElement => {

  const { name, hasShow, hasEdit } = useResourceDefinition(props)
  const { api } = useHttpClientContext()

  const [open] = useSidebarState()

  const [selectedRecord, setSelectedRecord] = useState<RaRecord>()

  const { id } = useParams()
  const operationId = useMemo(()=> relatedResource !== undefined && relatedResource !== '' ?`list_related_${name}_of_${relatedResource}`: `list_${name}`, [relatedResource, name])

  const { operation } = useResourceSchema(operationId)

  const fieldDefinitions = useFieldsForOperation(operationId, false, false)
  const fields = useMemo(()=>fieldDefinitions.map(def => createElement(def.component, def.props)),[fieldDefinitions])
  
  const fieldSchemas = useFilterInputForOperation(operationId)
  const filters = useMemo(() => fieldSchemas.map(def => createElement(def.component, def.props)), [fieldSchemas])
  
  const includeOptions = useMemo(() => (operation !== undefined) ? getIncludeOptions(operation) : [], [operation])
  const sparseFieldOptions = useMemo(() => (operation !== undefined) ? getSparseFieldOptions(operation) : [], [operation])

  const hasHistoricalEndpoint = useMemo(()=>Boolean(api?.getOperation(`list_Historical${name}`)),[api])

  const [listParams, setListParams] = useStore(`${name}.listParams`, {})
  const [searchParams, setSearchParams] = useSearchParams()
  const [availableColumns] = useStore<ConfigurableDatagridColumn[]>(`preferences.${name}.datagrid.availableColumns`, [])
  const [omit, setOmit ] = useStore<string[]>(`preferences.${name}.datagrid.omit`, defaultOmit)
  const [selectedColumnsIdxs] = useStore<string[]>(`preferences.${name}.datagrid.columns`, [])

  useEffect(()=>{
    const defaultShowColumns = ["stringRepresentation", "title", "abstract", "username", ...[rowActions && "actions"]]
    const wellDefinedColumns = availableColumns.map(col => col.source).filter(source => source !== undefined)    
    setOmit(wellDefinedColumns.filter(source => !defaultShowColumns.includes(source)))
  },[availableColumns])

  const sparseFieldsQueryValue = useMemo(
    () => availableColumns.filter(column => {
      if (column.source === undefined) return false
      
      return sparseFieldOptions.includes(column.source) &&
      selectedColumnsIdxs.length > 0 ? selectedColumnsIdxs.includes(column.index): !omit.includes(column.source)
     }
      ).map(column =>
      // TODO: django jsonapi has an open issue where no snake to cammel case translation are made
      // See https://github.com/django-json-api/django-rest-framework-json-api/issues/1053
      snakeCase(column.source)
    )
    , [sparseFieldOptions, availableColumns, selectedColumnsIdxs]
  )

  const includeQueryValue = useMemo(
    () => includeOptions.filter(includeOption => sparseFieldsQueryValue.includes(includeOption))
    , [sparseFieldsQueryValue, includeOptions]
  )

  const jsonApiQuery = useMemo(
    () => {
      const query: any = {}

      if (sparseFieldsQueryValue !== undefined) {
        query[`fields[${name}]`] = sparseFieldsQueryValue.join(',')
      }
      if (includeQueryValue !== undefined) {
        query.include = includeQueryValue.join(',')
      }

      return query
    }
    , [sparseFieldsQueryValue, includeQueryValue]
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
    <List
      filters={filters}
      actions={<ListActions filters={filters} />}
      queryOptions={{
        onError,
        meta: (relatedResource !== undefined && relatedResource !== '')
          ? {
            relatedResource: {
              resource: relatedResource,
              id
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
        <HistoryList
          resource={`Historical${name ?? ''}`}
          related={name ?? ''}
          record={selectedRecord}
          cardSx={
            {
              margin: '1em',
              height: 'calc(100vh - 110px - 1em)', // 174px ==> 50 appbar, 52 pagination,  1 em top padding
              width: `calc(${open ? '40vw' : '20vw'} - 1em - ${open ? '240px' : '50px'})`,
              overflowY: 'scroll'
            }
          }
        />: undefined
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

    </List >
  )
}

export default ListGuesser
