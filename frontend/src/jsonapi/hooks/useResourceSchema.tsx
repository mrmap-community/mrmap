import { useEffect, useState } from 'react'

import { type OpenAPIV3, type Operation } from 'openapi-client-axios'

import { SortPayload } from 'react-admin'
import { getEncapsulatedSchema } from '../openapi/parser'
import { getSortOptions, getSparseFieldOptionsPerResourceType } from '../utils'
import useOperation from './useOperation'

export interface OperationSchema {
  schema?: OpenAPIV3.NonArraySchemaObject
  operation?: Operation,
  sortValues?: SortPayload[],
  sparseFieldsPerResource?: {[key: string]: string[]}
}

const useResourceSchema = (operationId: string | undefined): OperationSchema => {
  const [schema, setSchema] = useState<OpenAPIV3.NonArraySchemaObject>()
  const [sortValues, setSortValues] = useState<SortPayload[]>([])
  const [sparseFieldsPerResource, setsparseFieldsPerResource] = useState<{[key: string]: string[]}>()

  const operation = useOperation(operationId)

  useEffect(() => {
    if (operation) {

      setSortValues(getSortOptions(operation))
      setsparseFieldsPerResource(getSparseFieldOptionsPerResourceType(operation))

      if (operation === undefined) {
        setSchema(undefined)
        return
      }
      const encapsulatedSchema = getEncapsulatedSchema(operation)
      setSchema({ ...encapsulatedSchema })

      
    }
  }, [operation])

  return { schema, operation, sortValues, sparseFieldsPerResource }
}

export default useResourceSchema
