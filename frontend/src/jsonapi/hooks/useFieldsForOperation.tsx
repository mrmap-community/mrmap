import { merge } from 'lodash';
import { useMemo } from 'react';
import { useHttpClientContext } from '../../context/HttpClientContext';
import { encapsulateFields, FieldDefinition, FieldSchema, getFieldDefinition, getFieldSchema } from '../utils';
import useResourceSchema from './useResourceSchema';

export interface FieldsForOperationProps {
  operationId: string
  ignoreId?: boolean
  forInput?: boolean
  overwrites?: FieldDefinition[] | undefined
}

export const useFieldsForOperation = (
  {
    operationId,
    ignoreId=true,
    forInput=true,
    overwrites=undefined
  }: FieldsForOperationProps
): FieldDefinition[] => {
  const { api } = useHttpClientContext()

  const {schema} = useResourceSchema(operationId)
  const allFields = useMemo(()=> schema && (ignoreId ? encapsulateFields(schema).filter(name => name !== 'id'): encapsulateFields(schema)) || [], [schema])
  const fieldSchemas = useMemo<FieldSchema[]>(()=> schema && allFields.map(name => getFieldSchema(name, schema)).filter(schema => schema !== undefined) || [], [schema, allFields])

  const fieldDefinitions = useMemo(() =>
    fieldSchemas.map(
      fieldSchema => {

        const definition = api && fieldSchema && getFieldDefinition(api, fieldSchema, forInput)
        const overwrite = overwrites?.find(overwrite => overwrite.props.source === definition?.props.source)
        if (!definition) return undefined
        merge(definition, overwrite)

        return definition
      }
    ).filter(
      fieldDefinition => fieldDefinition !== undefined
    ), [api, fieldSchemas, overwrites]
  )
  return fieldDefinitions
}