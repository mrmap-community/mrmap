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

/** One choice of an enum valued property, as the backend emits it in the
 * `x-enum-labels` extension (#1487): the enum value and the label it shows. */
export type EnumLabel = { value: unknown; label: unknown }

/** Schema extension carrying the display label of every enum value; the
 * precedents are `x-iso-path` and the `x-jsonapi-*` family (extras/schema.py). */
export const ENUM_LABELS_EXTENSION = 'x-enum-labels'

/** The choice contract of this layer is a numeric id: an entry only makes a
 * choice when its value is a non-negative integer (a number or such a string)
 * and it answers a label — the schema is external input, everything else of
 * an entry is dropped as before. */
const toChoice = (entry?: EnumLabel): { id: number; name: string } | undefined => {
  const value = entry?.value
  const label = entry?.label
  const id = typeof value === 'number' ? value
    : typeof value === 'string' && /^\d+$/.test(value) ? Number.parseInt(value, 10)
    : undefined
  if (id === undefined || !Number.isInteger(id) || id < 0) return undefined
  if (typeof label !== 'string' || label === '') return undefined
  return { id, name: label }
}

/** The choices of an enum valued property: the structured labels the backend
 * emits, never a parsing of the description prose — that wording belongs to
 * drf-spectacular and silently dropped the choices when it changed (#1487). */
export const buildChoices = (property: OpenAPIV3.SchemaObject): { id: number; name: string }[] => {
  const labels = property?.[ENUM_LABELS_EXTENSION as keyof OpenAPIV3.SchemaObject] as EnumLabel[] | undefined
  if (!Array.isArray(labels)) return []
  return labels.map(toChoice).filter(choice => choice !== undefined)
}

/** The JSON:API type of the records a nested list operation answers with: the enum
 *  of the `type` of its items. A nested route needs exactly this to register the
 *  related resource, so the nesting is read here and not in the screen that asks. */
export const getRelatedResourceType = (operation: AxiosOperation): string | undefined => {
  const resourceSchema = getResourceSchema(operation)

  const properties = resourceSchema?.properties?.data as OpenAPIV3.ArraySchemaObject
  const items = properties?.items as OpenAPIV3.SchemaObject
  const jsonApiTypeProperty = items?.properties?.type as OpenAPIV3.NonArraySchemaObject
  const jsonApiTypeReferences = jsonApiTypeProperty?.allOf as OpenAPIV3.SchemaObject[]
  return jsonApiTypeReferences?.[0]?.enum?.[0] as string | undefined
}

/** Index nested operations by their exact parent resource, in schema order. */
export const indexRelatedOperations = (operations: AxiosOperation[]): Map<string, AxiosOperation[]> => {
  const related = new Map<string, AxiosOperation[]>();
  for (const operation of operations) {
    const parent = operation.operationId?.match(/_of_(.+)$/)?.[1];
    if (!parent) continue;
    const entries = related.get(parent) ?? [];
    entries.push(operation);
    related.set(parent, entries);
  }
  return related;
};
