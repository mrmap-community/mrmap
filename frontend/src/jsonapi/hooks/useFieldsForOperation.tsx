import { useMemo } from 'react';
import { useHttpClientContext } from '../../context/HttpClientContext';
import { encapsulateFields, FieldDefinition, FieldSchema, getFieldDefinition, getFieldSchema } from '../utils';
import useResourceSchema from './useResourceSchema';



export const useFieldsForOperation = (
  operationId: string,
  ignore_id = true,
  forInput = true
): FieldDefinition[] => {
  const { api } = useHttpClientContext()

  const {schema} = useResourceSchema(operationId)
  const allFields = useMemo(()=> schema && (ignore_id ? encapsulateFields(schema).filter(name => name !== 'id'): encapsulateFields(schema)) || [], [schema])
  const fieldSchemas = useMemo<FieldSchema[]>(()=> schema && allFields.map(name => getFieldSchema(name, schema)).filter(schema => schema !== undefined) || [], [schema, allFields])

  const fieldDefinitions = useMemo(() =>
    fieldSchemas.map(
      fieldSchema => api && fieldSchema && getFieldDefinition(api, fieldSchema, forInput))
        .filter(fieldDefinition => fieldDefinition !== undefined),
        [api, fieldSchemas]
  )

  return fieldDefinitions
}