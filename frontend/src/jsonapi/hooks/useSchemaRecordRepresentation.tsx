import { useCallback, useEffect, useState } from 'react'
import { type RaRecord, RecordToStringFunction, useResourceDefinition } from 'react-admin'

import { type OpenAPIV3 } from 'openapi-client-axios'

import useResourceSchema from './useResourceSchema'

export interface SchemaRecordRepresentationProps {
  operationId?: string
  resource?: string
}

const getRecordRepresentationFromSchema = (schema: OpenAPIV3.NonArraySchemaObject): string => {
  let recordRepresentation = 'id'

  const jsonApiPrimaryDataProperties = schema?.properties as Record<string, OpenAPIV3.NonArraySchemaObject>
  const jsonApiResourceAttributes = jsonApiPrimaryDataProperties?.attributes?.properties as OpenAPIV3.NonArraySchemaObject
  // TODO: change the check to a simpler way
  if (jsonApiResourceAttributes !== undefined) {
    if (Object.entries(jsonApiResourceAttributes).find(([key, value]) => key === 'stringRepresentation') != null) {
      recordRepresentation = 'stringRepresentation'
    } else if (Object.entries(jsonApiResourceAttributes).find(([key, value]) => key === 'title') != null) {
      recordRepresentation = 'title'
    } else if (Object.entries(jsonApiResourceAttributes).find(([key, value]) => key === 'name') != null) {
      recordRepresentation = 'name'
    }
  }

  return recordRepresentation
}

const useSchemaRecordRepresentation = (
  {
    operationId,
    resource
  }: SchemaRecordRepresentationProps
): RecordToStringFunction => {
  const { name } = useResourceDefinition({resource: resource})
  const { schema } = useResourceSchema(operationId ?? `list_${name}`)
  
  const [representation, setRepresentation] = useState<string>()
  
  const optionTextFunc = useCallback((record: RaRecord) => {
    if (representation !== undefined) {
      return Object.hasOwn(record, representation) ? record[representation] : `${name} (${record.id})`
    } else {
      return `${name} (${record.id})`
    }
  }, [representation, name])

  useEffect(() => {
    if (schema !== undefined) {
      const rep = getRecordRepresentationFromSchema(schema)
      setRepresentation(rep)
    }
  }, [schema])

  return optionTextFunc
}

export default useSchemaRecordRepresentation
