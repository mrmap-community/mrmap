import { snakeCase } from "lodash"
import { useMemo } from "react"
import { ConfigurableDatagridColumn, useResourceDefinition, useStore } from "react-admin"
import { SparseFieldsets } from "../types/jsonapi"
import { getIncludeOptions, getSparseFieldOptions } from "../utils"
import useResourceSchema from "./useResourceSchema"


export interface UseJsonApiQueryProps {
    relatedResource?: string
}


const useJsonApiQuery = ({
    relatedResource,
}: UseJsonApiQueryProps) => {

  const { name, options } = useResourceDefinition()
  const listOptions = useMemo(()=>(options.list),[options])
  
  const operationId = useMemo(()=> relatedResource !== undefined && relatedResource !== '' ?`list_related_${name}_of_${relatedResource}`: `list_${name}`, [relatedResource, name])
  const { operation } = useResourceSchema(operationId)
  const preferenceKey = useMemo(()=>(`${operationId}.datagrid`),[operationId])

  const includeOptions = useMemo(() => (operation !== undefined) ? getIncludeOptions(operation) : [], [operation])
  const sparseFieldOptions = useMemo(() => (operation !== undefined) ? getSparseFieldOptions(operation) : [], [operation])
 
  const [availableColumns] = useStore<ConfigurableDatagridColumn[]>(`preferences.${preferenceKey}.availableColumns`, [])
  const [omit] = useStore<string[]>(`preferences.${preferenceKey}.omit`)
  const [selectedColumnsIdxs] = useStore<string[]>(`preferences.${preferenceKey}.columns`, [])


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
      const _sparseFieldsets = listOptions?.sparseFieldsets || []
      _sparseFieldsets.forEach((sf: SparseFieldsets) => {
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
      

      if (_sparseFieldsets === undefined && sparseFieldsQueryValue !== undefined) {
        query[`fields[${name}]`] = sparseFieldsQueryValue.join(',')
      }

      if (includeQueryValue !== undefined) {
        query.include = includeQueryValue.join(',')
      }

      return query
    }
    , [listOptions?.sparseFieldsets, sparseFieldsQueryValue, includeQueryValue])


    return jsonApiQuery
}



export default useJsonApiQuery