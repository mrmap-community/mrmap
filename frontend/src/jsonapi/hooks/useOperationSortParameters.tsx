import { useMemo } from 'react'

import { ParameterObject, type OpenAPIV3, type Operation } from 'openapi-client-axios'

import { SortPayload } from 'react-admin'
import useOperation from './useOperation'

export interface OperationSortParameters {
  sortPayload?: SortPayload[]
  operation?: Operation
}

const useOperationSortParameters = (operationId: string): OperationSortParameters => {

  const operation = useOperation(operationId)
  
  const sortPayload = useMemo<SortPayload[]>(()=>{
    const sortParameter = operation?.parameters?.find((parameter) => {
      const p = parameter as ParameterObject
      return p.name === "sort"
    }) as ParameterObject
    const sortParameterSchema = sortParameter?.schema as OpenAPIV3.ArraySchemaObject
    const sortParameterItems = sortParameterSchema?.items as OpenAPIV3.NonArraySchemaObject
    
    return sortParameterItems?.enum?.map(sP => {
      
      const splitted = sP.split("-")
      
      return {field: splitted.length > 1 ? splitted[1]: splitted[0], order: splitted.length > 1 ? 'DESC': 'ASC'}
    }) || []

  },[operation])


  return { sortPayload, operation }
}

export default useOperationSortParameters
