import { ArrayField, ArrayInput, AutocompleteArrayInput, BooleanField, BooleanInput, ChipField, DateField, DateInput, DateTimeInput, EmailField, NumberField, NumberInput, SelectField, SelectInput, SingleFieldList, SortPayload, TextField, TextInput, TimeInput, UrlField, type RaRecord } from 'react-admin'
import {
  email,
  maxLength,
  minLength,
  regex
} from 'react-admin'

import OpenAPIClientAxios, { type OpenAPIV3, type Operation, type ParameterObject } from 'openapi-client-axios'

import CreateSuggestionDialog from '../components/Dialog/CreateSuggestionDialog'
import GeoJsonField from '../components/Field/GeoJsonField'
import TruncatedTextField from '../components/Field/TruncatedTextField'
import GeoJsonInput from '../components/Input/GeoJsonInput'
import JsonApiReferenceField from './components/ReferenceField'
import JsonApiReferenceManyField from './components/ReferenceManyField'
import SchemaAutocompleteInput from './components/SchemaAutocompleteInput'
import { buildChoices, getEncapsulatedSchema } from './openapi/parser'
import { type JsonApiDocument, type JsonApiPrimaryData, type ResourceLinkage } from './types/jsonapi'

export interface FieldSchema {
  name: string
  reference?: string
  resource: string
  schema: OpenAPIV3.SchemaObject
  isRequired: boolean
  isReadOnly: boolean
  /** The ISO 19139 element path the backend stamps on writable mapped fields
   *  (#1240); present only on the fields the write mapper can actually write. */
  isoPath?: string
  kind: 'attribute' | 'relationship' |'array-relationship'
}

export interface FieldDefinition {
  component: import("react").ElementType,
  props: {
    source: string
    label?: string
    reference?: string
    helperText?: import("react").ReactNode
    choices?: { id: unknown; name: string }[]
    validate?: import("react-admin").Validator[]
    [key: string]: unknown
  }
}


/** json:api linkage for one relationship taken out of the record: a to-many
 *  relation links all of its records, a single one links none when absent */
const relationshipLinkage = (
  relationName: string,
  resourceLinkageSchema: OpenAPIV3.NonArraySchemaObject,
  attributes: Record<string, unknown>
): ResourceLinkage | undefined => {
  // need to capsulate data of relationship as well
  const data = resourceLinkageSchema.properties?.data as OpenAPIV3.NonArraySchemaObject & { items?: OpenAPIV3.NonArraySchemaObject }
  const isList = Object.hasOwn(data, 'items')
  const relationSchema = (isList ? data.items : data) as OpenAPIV3.NonArraySchemaObject
  const relationResourceType = relationSchema?.properties?.type as OpenAPIV3.NonArraySchemaObject

  if (isList) {
    const relationData: RaRecord[] = attributes[relationName] as RaRecord[]
    return { data: relationData.map((record: RaRecord) => ({ id: record.id, type: relationResourceType?.enum?.[0] })) }
  }
  const relationData: RaRecord = attributes[relationName] as RaRecord
  if (relationData === undefined || relationData === null) return undefined
  return { data: { id: relationData.id, type: relationResourceType?.enum?.[0] } }
}

export const capsulateJsonApiPrimaryData = (data: Partial<RaRecord>, type: string, operation: Operation): JsonApiPrimaryData => {
  /** helper to transform react admin data to json:api conform primary data object
     *
     */
  const { id, ...attributes } = data
  const relationships: Record<string, ResourceLinkage> = {}

  const resourceSchema = getEncapsulatedSchema(operation)

  const jsonApiPrimaryDataProperties = resourceSchema?.properties as Record<string, OpenAPIV3.NonArraySchemaObject>
  const jsonApiResourceRelationships = jsonApiPrimaryDataProperties?.relationships?.properties as OpenAPIV3.NonArraySchemaObject
  for (const [relationName, resourceLinkageSchema] of Object.entries(jsonApiResourceRelationships ?? {})) {
    if (!(relationName in attributes)) continue
    const linkage = relationshipLinkage(relationName, resourceLinkageSchema, attributes)
    if (linkage) relationships[relationName] = linkage
    // FUTURE: delete attributes.relationName does not work (no-dynamic-delete)
    delete attributes[relationName]  
  }

  const primaryData: JsonApiPrimaryData = {
    id: id!,
    type,
    attributes,
    ...(Object.keys(relationships).length > 0 && {relationships: relationships})
  }
  return primaryData
}

export const encapsulateJsonApiRelationship = (
  relationships: Record<string, ResourceLinkage>,
  allRecords: Record<string, RaRecord>,
  currentRecordId: string,
  preventCircular = false
) => {
  const linkId = (type: string, id: string | number) => `${type}:${id}`

  const buildRef = (id: string | number) => ({ id })

  const mergeRecord = (id: string | number, type: string) => {
    const key = linkId(type, id)
    allRecords[key] = {
      ...allRecords[key],
      id
    }
    return allRecords[key]
  }

  const handleItem = (item: import("./types/jsonapi").ResourceIdentifierObject) => {
    if (preventCircular) return buildRef(item.id)
    return mergeRecord(item.id, item.type)
  }

  for (const [relationName, resourceLinkage] of Object.entries(relationships || {})) {
    const data = resourceLinkage.data
    if (!data) continue

    const target = allRecords[currentRecordId]

    if (Array.isArray(data)) {
      target[relationName] = data.map(item =>
        handleItem(item)
      )
    } else {
      target[relationName] = handleItem(data)
    }
  }
}

/** Normalize included resources once per response, retaining id-only nested relationships. */
export const encapsulateJsonApiDocumentData = (
  document: JsonApiDocument | undefined,
  resources: JsonApiPrimaryData[],
): RaRecord[] => {
  const included: Record<string, RaRecord> = {};
  document?.included?.forEach(data => {
    const key = `${data.type}:${data.id}`;
    included[key] = { id: data.id, ...data.attributes };
    encapsulateJsonApiRelationship(data.relationships ?? {}, included, key, true);
  });

  return resources.map(data => {
    const key = `${data.type}:${data.id}`;
    // A per-record overlay keeps relationship expansion isolated without copying the lookup.
    const records: Record<string, RaRecord> = Object.create(included);
    records[key] = { ...(included[key] ?? { id: data.id, ...data.attributes }) };
    encapsulateJsonApiRelationship(data.relationships ?? {}, records, key);
    return records[key];
  });
};

export const encapsulateJsonApiPrimaryData = (
  document: JsonApiDocument | undefined,
  data: JsonApiPrimaryData,
): RaRecord => encapsulateJsonApiDocumentData(document, [data])[0];

export const getIncludeOptions = (operation: Operation): string[] => {
  if (operation !== undefined) {
    const parameters = operation.parameters as ParameterObject[]
    const includeParameterSchema = parameters?.find((parameter) => parameter.name.includes('include'))?.schema as OpenAPIV3.ArraySchemaObject
    const includeParameterArraySchema = includeParameterSchema?.items as OpenAPIV3.SchemaObject
    return includeParameterArraySchema?.enum ?? []
  }
  return []
}

// deprecated
// different ResourceTypes are possible; This function does not extract sparse fields for different ResourceTypes!
export const getSparseFieldOptions = (operation: Operation): string[] => {
  if (operation !== undefined) {
    const parameters = operation.parameters as ParameterObject[]
    const sparseFieldParameterSchema = parameters?.find((parameter) => parameter.name.includes('fields['))?.schema as OpenAPIV3.ArraySchemaObject
    const sparseFieldParameterArraySchema = sparseFieldParameterSchema.items as OpenAPIV3.SchemaObject
    return sparseFieldParameterArraySchema.enum ?? []
  }
  return []
}

export const getSparseFieldOptionsPerResourceType = (operation?: Operation): {[key: string]: string[]} => {
  const sparseFieldParametersPerType: {[key: string]: string[]} = {}

  if (operation !== undefined) {
    const parameters = operation.parameters as ParameterObject[]

    parameters?.filter((parameter) => parameter.name.includes('fields[')).forEach((parameterObject)=>{
      const name = parameterObject.name;
      const start = name.indexOf('[');
      const end = start === -1 ? -1 : name.indexOf(']', start + 1);
      const resourceType = end === -1
        ? undefined
        : name.slice(start + 1, end);
      const schema = parameterObject.schema as OpenAPIV3.ArraySchemaObject
      const sparseFieldParameterArraySchema = schema.items as OpenAPIV3.SchemaObject
      const fields = sparseFieldParameterArraySchema.enum ?? []
      if (resourceType !== undefined && fields.length > 0){
        sparseFieldParametersPerType[resourceType] = fields
      }
    })
  }
  
  return sparseFieldParametersPerType
}

export const getSortOptions = (operation?: Operation): SortPayload[] => {
  const sortFieldParameters: SortPayload[] = []
  if (operation !== undefined) {
    const parameters = operation.parameters as ParameterObject[]
    const sparseFieldParameterSchema = parameters?.find((parameter) => parameter.name.includes('sort'))?.schema as OpenAPIV3.ArraySchemaObject
    const sparseFieldParameterArraySchema = sparseFieldParameterSchema?.items as OpenAPIV3.SchemaObject
    
    
    const values = sparseFieldParameterArraySchema?.enum ?? []

    values.forEach((value) => {
      sortFieldParameters.push({
        field: value.startsWith('-') ? value.substring(1) : value,
        order: value.startsWith('-') ? 'DESC' : 'ASC'
      });
    });
  }
  
  return sortFieldParameters
}


export const hasIncludedData = (record: RaRecord): boolean => (Object.entries(record).some(([name]) => name !== 'id'))


export const encapsulateFields = (schema: OpenAPIV3.NonArraySchemaObject) => {

  const jsonApiPrimaryDataProperties = schema?.properties as Record<string, OpenAPIV3.NonArraySchemaObject>
  const jsonApiResourceAttributes = jsonApiPrimaryDataProperties?.attributes?.properties 
  const jsonApiResourceRelationships = jsonApiPrimaryDataProperties?.relationships?.properties
  const jsonApiResourceId = jsonApiPrimaryDataProperties?.id as Record<string, OpenAPIV3.NonArraySchemaObject>

  return [
    ...(jsonApiResourceAttributes && Object.keys(jsonApiResourceAttributes) || []),
    ...(jsonApiResourceRelationships && Object.keys(jsonApiResourceRelationships) || []),
    ...(jsonApiResourceId && ['id'] || [])
  ]

};

/** The OpenAPI extension (#1240) carrying the ISO 19139 element path of a
 *  writable mapped field, stamped by the backend's postprocessing hook. */
export const ISO_PATH_EXTENSION = 'x-iso-path'

export const getIsoPath = (property: OpenAPIV3.SchemaObject | undefined): string | undefined => {
  const value = property?.[ISO_PATH_EXTENSION as keyof OpenAPIV3.SchemaObject]
  return typeof value === 'string' ? value : undefined
}

export const getFieldSchema = (name: string, schema: OpenAPIV3.NonArraySchemaObject): FieldSchema | undefined => {
  const jsonApiPrimaryDataProperties = schema?.properties as Record<string, OpenAPIV3.NonArraySchemaObject>
  const jsonApiResourceAttributes = jsonApiPrimaryDataProperties?.attributes?.properties 
  const jsonApiResourceRelationships = jsonApiPrimaryDataProperties?.relationships?.properties
  const jsonApiResourceTypeRef = jsonApiPrimaryDataProperties?.type?.allOf as OpenAPIV3.ArraySchemaObject[]
  const jsonApiResourceType = jsonApiResourceTypeRef?.[0].enum?.[0]
  const jsonApiResourceId = jsonApiPrimaryDataProperties?.id

  const isRequired = jsonApiPrimaryDataProperties?.attributes?.required?.includes(name) ??
                      jsonApiPrimaryDataProperties?.relationships?.required?.includes(name) ?? 
                      false
  

    if (name === "id" && jsonApiResourceId !== undefined) {
      // on create operations there is no id
      return {
        name: name, 
        resource: jsonApiResourceType,
        schema: jsonApiResourceId,
        isRequired: schema?.required?.includes('id') ?? false, 
        isReadOnly: jsonApiResourceId.readOnly ?? false,
        kind: 'attribute'
      }
    }

    if (jsonApiResourceAttributes && Object.hasOwn(jsonApiResourceAttributes, name)) {
      const s = jsonApiResourceAttributes?.[name] as OpenAPIV3.NonArraySchemaObject
      return {
        name: name, 
        resource: jsonApiResourceType,
        schema: s, 
        isRequired: isRequired,
        isReadOnly: s?.readOnly ?? false,
        isoPath: getIsoPath(s),
        kind: 'attribute'
      }
    }

    if (jsonApiResourceRelationships && Object.hasOwn(jsonApiResourceRelationships, name)) {
      const relationSchema = jsonApiResourceRelationships?.[name] as OpenAPIV3.SchemaObject
      const relationDataSchema = relationSchema?.properties?.data as OpenAPIV3.SchemaObject
      
      if (relationDataSchema?.type === 'array') {
        const _relationSchema = relationDataSchema.items as OpenAPIV3.NonArraySchemaObject
        const type = _relationSchema?.properties?.type as OpenAPIV3.NonArraySchemaObject
        return {
          name: name, 
          reference: type?.enum?.[0],
          resource: jsonApiResourceType,
          schema: _relationSchema,
          isRequired: isRequired,
          isReadOnly: relationSchema.readOnly ?? false,
          isoPath: getIsoPath(relationSchema),
          kind: 'array-relationship'
        }
      } else {
        const _relationSchema = relationSchema?.properties?.data as OpenAPIV3.NonArraySchemaObject
        const type = _relationSchema?.properties?.type as OpenAPIV3.NonArraySchemaObject
        return {
          name: name, 
          reference: type?.enum?.[0],
          resource: jsonApiResourceType,
          schema: relationSchema as OpenAPIV3.NonArraySchemaObject,
          isRequired: isRequired, 
          isReadOnly: relationSchema.readOnly ?? false,
          isoPath: getIsoPath(relationSchema),
          kind: 'relationship'
        }
      }
        
    }
};

/** the choices a simple enum array offers to an input that can pick from them */
const nestedArrayChoices = (
  nestedSchema: OpenAPIV3.SchemaObject,
  forInput: boolean
) => {
  const enumValues = nestedSchema.enum
  if (!forInput || !Array.isArray(enumValues)) return undefined
  const choices = enumValues.map(choice => ({ id: choice, name: choice }))
  return choices.length > 0 ? choices : undefined
}

export const getArrayInput = (
  source: string, 
  schema: OpenAPIV3.ArraySchemaObject, 
  isRequired: boolean = false, 
  isReadOnly: boolean = false, 
  forInput: boolean = true
): FieldDefinition => {
  
  const definition: FieldDefinition = {
    component: forInput ? ArrayInput: ArrayField,
    props: {
      source: source,
      label: schema.title ?? source,
      disabled: isReadOnly?? false,
      ...(schema.default && {defaultValue: schema.default}),
      ...(forInput && {required: isRequired}),
      ...(forInput && schema.description && {helperText: schema.description}),
    }
  }

  const nestedSchema = schema.items as OpenAPIV3.SchemaObject

  const choices = nestedArrayChoices(nestedSchema, forInput)

  if (choices){
    // simple choice input
    definition.component = AutocompleteArrayInput;
    definition.props.choices = choices;
  } else if (nestedSchema.type === 'object') {
    // FUTURE: nested resource
    // 1. get all nested fields of this object...
    // 2. create all nested fields...
    // 3. set children prop
    definition.component = forInput ? TextInput : TextField;
    console.debug(`nested resoruces are not supported for now. Source: ${source}`);
  } else if (!forInput) {
    // single array of simple typed field
    definition.props.children = (
      <SingleFieldList linkType={false}>
        <ChipField source={source} size="small" />
      </SingleFieldList>
    ) 
  } else {
      // this results in form field states like 
      /**
       * { source: [
       *    {source: 'huhu'}, {source: 'huhu'}, {source: 'huhu'}
       *   ]
       * }
      
      const field = getFieldForType(source, 
                                    nestedSchema, 
                                    isRequired,
                                    isReadOnly,
                                    forInput)
  
      definition.props.children =  (
        <SimpleFormIterator>
          {createElement(field.component, field.props)}
        </SimpleFormIterator>
      ) */
      definition.component = forInput ? TextInput : TextField;

  }
  return definition;
}

/** the text field a schema maps to before its format or type say more about it */
const textFieldDefinition = (
  source: string,
  schema: OpenAPIV3.SchemaObject,
  isRequired: boolean,
  isReadOnly: boolean,
  forInput: boolean
): FieldDefinition => {
  const validate = [
    ... schema.maxLength ? [maxLength(schema.maxLength)] : [],
    ... schema.minLength ? [minLength(schema.minLength)] : [],
    ... schema.pattern ? [regex(new RegExp(schema.pattern))] : []
  ]

  return {
    component: forInput ? TextInput : TextField,
    props: {
      source: source,
      label: schema.title ?? source,
      disabled: isReadOnly ?? false,
      ...(schema.default && {defaultValue: schema.default}),
      ...(validate.length > 0 && {validate: validate}),
      ...(forInput && {required: isRequired}),
      ...(forInput && schema.description && {helperText: schema.description}),
    }
  }
}

/** what each schema format adds to the default text field: the components it
 *  calls for, whether they show a time and which validators they bring. The
 *  components and validators are named behind calls so that a field of another
 *  format never builds one it does not ask for.
 *  FUTURE: is there a duration input? https://mui.com/x/react-date-pickers/ */
const formatFields: Record<string, {
  input: () => import("react").ElementType,
  display: () => import("react").ElementType,
  showTime?: boolean,
  validators?: () => import("react-admin").Validator[]
}> = {
  'date-time': { input: () => DateTimeInput, display: () => DateField, showTime: true },
  'date': { input: () => DateInput, display: () => DateField },
  'time': { input: () => TimeInput, display: () => DateField, showTime: true },
  'duration': { input: () => TextInput, display: () => TextInput },
  'uri': {
    input: () => TextInput,
    display: () => UrlField,
    validators: () => [regex(/^(http(s?):\/\/.)[-a-zA-Z0-9@:%._+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_+.~#?&/=]*)$/)]
  },
  'email': { input: () => TextInput, display: () => EmailField, validators: () => [email()] },
  'geojson': { input: () => GeoJsonInput, display: () => GeoJsonField },
}

export const getFieldForFormat = (
  source: string, 
  schema: OpenAPIV3.SchemaObject, 
  isRequired: boolean = false, 
  isReadOnly: boolean = false, 
  forInput: boolean = true
): FieldDefinition => {
  const definition = textFieldDefinition(source, schema, isRequired, isReadOnly, forInput)

  // See https://datatracker.ietf.org/doc/html/draft-bhutton-json-schema-validation-01#name-defined-formats for valid schema.format strings
  const format = schema.format === undefined ? undefined : formatFields[schema.format]
  if (format === undefined) return definition

  definition.component = forInput ? format.input() : format.display()
  if (format.showTime) definition.props.showTime = true
  if (format.validators !== undefined) definition.props.validate = [
    ...(definition.props.validate ?? []),
    ...format.validators()
  ]
  return definition
}


export const getFieldForType = (
  source: string, 
  schema: OpenAPIV3.SchemaObject, 
  isRequired: boolean = false, 
  isReadOnly: boolean = false, 
  forInput: boolean = true): FieldDefinition => {
  
  const definition = textFieldDefinition(source, schema, isRequired, isReadOnly, forInput)

  if (schema.enum !== undefined) {
    const choices = buildChoices(schema)
    if (choices.length > 0){
      definition.component = forInput ? SelectInput: SelectField;
      definition.props.choices = choices;
      return definition;
    }
  }

  switch(schema.type) {
    case 'integer':
    case 'number':
      definition.component = forInput ? NumberInput: NumberField;
      if (schema.maximum !== undefined) definition.props.max = schema.maximum;
      if (schema.minimum !== undefined) definition.props.min = schema.minimum;
      break;
    case 'boolean':
      definition.component = forInput ? BooleanInput: BooleanField;
      definition.props.defaultValue = schema.default ?? false;
      break;
    case 'string':
      return getFieldForFormat(
        source,
        schema, 
        isRequired,
        isReadOnly,
        forInput);
    case 'array':
      return getArrayInput(
        source, 
        schema, 
        isRequired,
        isReadOnly,
        forInput);
  }

  return definition;
}

/** the field of a single relation: an autocomplete that may offer to create
 *  the related record, a plain reference otherwise */
const relationshipFieldDefinition = (
  api: OpenAPIClientAxios,
  fieldSchema: FieldSchema,
  commonProps: FieldDefinition['props'],
  forInput: boolean
): FieldDefinition => {
  const hasCreate = api.getOperation(`create_${fieldSchema.reference}`) !== undefined
  return {
    component: forInput ? SchemaAutocompleteInput: JsonApiReferenceField, 
    props: {
      ...commonProps, 
      ...(forInput ? 
        {
          target: fieldSchema.name, 
          link: 'edit', 
          ...(hasCreate && {
            create: <CreateSuggestionDialog guesserProps={{
              resource: fieldSchema.reference
            }}/>,
            createLabel: 'type something to create a new object', // FUTURE: use translate
            sort:{ field: 'name', order: 'ASC' }
          })
        }: 
        {
          reference: fieldSchema.reference, 
          target: fieldSchema.resource,
        })
    }
  }
}

/** the field of a to-many relation: a multiple autocomplete on input, a
 *  reference list otherwise */
const arrayRelationshipFieldDefinition = (
  fieldSchema: FieldSchema,
  commonProps: FieldDefinition['props'],
  forInput: boolean
): FieldDefinition => {
  const props: FieldDefinition['props'] = {
    ...commonProps,
    ...(forInput ? {multiple: true}: {reference: fieldSchema.reference, target: fieldSchema.resource,})
  }

  return {
    component: forInput ? SchemaAutocompleteInput: JsonApiReferenceManyField, 
    props: {
      ...props,
      // an absent defaultValue would answer null values and TypeErrors on => undefined.map()
      defaultValue: props.defaultValue ?? [],
      reference: fieldSchema.reference,
      target: fieldSchema.resource,
    }
  }
}

export const getFieldDefinition = (api: OpenAPIClientAxios, fieldSchema: FieldSchema, forInput: boolean = true): FieldDefinition | undefined => {
  const commonProps: FieldDefinition['props'] = {
    source: fieldSchema.name,
    label: fieldSchema.schema.title ?? fieldSchema.name,
    disabled: fieldSchema.isReadOnly?? false,
    ...(fieldSchema.schema.default && {defaultValue: fieldSchema.schema.default}),
    ...(fieldSchema.schema.description && {helperText: fieldSchema.schema.description}),
    ...(forInput && {required: fieldSchema.isRequired}),
    ...(fieldSchema.reference && {reference: fieldSchema.reference})
  }

  if (fieldSchema?.kind === 'attribute'){
    return getFieldForType(
      fieldSchema.name, 
      fieldSchema.schema, 
      fieldSchema.isRequired,
      fieldSchema.isReadOnly ?? false,
      forInput
    )
  } else if (fieldSchema?.kind === 'relationship' ) {
    return relationshipFieldDefinition(api, fieldSchema, commonProps, forInput)
  } else if (fieldSchema?.kind === 'array-relationship') {   
    return arrayRelationshipFieldDefinition(fieldSchema, commonProps, forInput)
  }

  // default fallback
  return {
    component: forInput ? TextInput: TruncatedTextField, 
    props: {textOverflow: 'ellipsis', ...commonProps}
  }
}

export const parseDuration = (duration:string): number => {
  // Zerlege den Input-String mit einem regulären Ausdruck
  const regex = /^(\d{1,2})?\s*(\d{1,2})?:?(\d{2})?:?(\d{2})\.(\d{6})$/;
  const matches = regex.exec(duration);
  if (matches) {
      // Extrahiere Tage, Stunden, Minuten, Sekunden und Mikrosekunden
      const days = matches[1] ? Number.parseInt(matches[1], 10) : 0; // Standardwert 0, wenn kein Tag vorhanden
      const hours = matches[2] ? Number.parseInt(matches[2], 10) : 0; // Standardwert 0, wenn keine Stunde angegeben
      const minutes = matches[3] ? Number.parseInt(matches[3], 10) : 0; // Standardwert 0, wenn keine Minuten angegeben
      const seconds = Number.parseInt(matches[4], 10); // Sekunden sind immer da, daher keine Option
      const microseconds = Number.parseInt(matches[5], 10); // Mikrosekunden sind immer da
  

      // Berechne die Gesamtzeit in Sekunden
      const totalSeconds = (days * 24 * 60 * 60) + (hours * 3600) + (minutes * 60) + seconds + (microseconds / 1000000);

      return Math.round(totalSeconds);
  } else {
      return 0
  }
}
