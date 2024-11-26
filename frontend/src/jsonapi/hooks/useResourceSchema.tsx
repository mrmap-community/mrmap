import { useEffect, useState } from 'react'

import { type OpenAPIV3, type Operation } from 'openapi-client-axios'

import { getEncapsulatedSchema } from '../openapi/parser'
import useOperation from './useOperation'

export interface OperationSchema {
  schema?: OpenAPIV3.NonArraySchemaObject
  operation?: Operation
}

const useResourceSchema = (operationId: string): OperationSchema => {
  const [schema, setSchema] = useState<OpenAPIV3.NonArraySchemaObject>()

  const operation = useOperation(operationId)

  useEffect(() => {
    if (operation) {
      if (operation === undefined) {
        setSchema(undefined)
        return
      }
      const encapsulatedSchema = getEncapsulatedSchema(operation)
      setSchema({ ...encapsulatedSchema })
    }
  }, [operation])

  return { schema, operation }
}

export default useResourceSchema
