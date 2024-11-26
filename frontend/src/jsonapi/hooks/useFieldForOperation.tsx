import { useMemo } from 'react'
import { useHttpClientContext } from '../../context/HttpClientContext'
import { FieldDefinition, FieldSchema, getFieldDefinition, getFieldSchema } from '../utils'
import useResourceSchema from './useResourceSchema'


const useFieldForOperation = (
  name: string, 
  operationId: string,

): FieldDefinition | undefined => {
  const {schema} = useResourceSchema(operationId)
  const { api } = useHttpClientContext()

  const fieldSchema = useMemo<FieldSchema | undefined>(()=> schema && getFieldSchema(name, schema), [schema, name])
    
  return api && fieldSchema && getFieldDefinition(api, fieldSchema)
}

export default useFieldForOperation
