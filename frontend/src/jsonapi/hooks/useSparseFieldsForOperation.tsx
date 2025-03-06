import { useMemo } from 'react'

import { type Operation } from 'openapi-client-axios'

import { getSparseFieldOptionsPerResourceType } from '../utils'
import useOperation from './useOperation'


export interface SparseFieldsMap {
  [key: string]: string[]
}

export interface OperationSortParameters {
  sparseFields: SparseFieldsMap
  operation?: Operation
}

const useSparseFieldsForOperation = (operationId: string): OperationSortParameters => {

  const operation = useOperation(operationId)
  const sparseFields = useMemo<{[key: string]: string[]}>(()=>getSparseFieldOptionsPerResourceType(operation),[operation])

  return { sparseFields, operation }
}

export default useSparseFieldsForOperation
