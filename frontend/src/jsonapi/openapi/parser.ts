import { type Operation as AxiosOperation } from 'openapi-client-axios'
import { type OpenAPIV3 } from 'openapi-types'

export const getResourceSchema = (operation: AxiosOperation): OpenAPIV3.SchemaObject | undefined => {
  if (operation?.method === 'get') {
    const responseObject = operation?.responses?.['200'] as OpenAPIV3.ResponseObject
    return responseObject?.content?.['application/vnd.api+json']?.schema as OpenAPIV3.SchemaObject
  } else if (operation?.method === 'put' || operation?.method === 'post' || operation?.method === 'patch') {
    const requestObject = operation?.requestBody as OpenAPIV3.RequestBodyObject
    return requestObject?.content?.['application/vnd.api+json']?.schema as OpenAPIV3.SchemaObject
  }
}

export const getEncapsulatedSchema = (operation: AxiosOperation): OpenAPIV3.NonArraySchemaObject => {
  /** helper function to return the encapsulated openapi schema of the jsonapi resource
   *
   */
  const schema = getResourceSchema(operation)
  const primaryDataSchema = schema?.properties?.data as OpenAPIV3.SchemaObject

  const isList = primaryDataSchema?.type === 'array'
  if (isList) {
    return primaryDataSchema.items as OpenAPIV3.NonArraySchemaObject
  } else {
    return primaryDataSchema
  }
}
