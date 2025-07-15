import OpenAPIClientAxios, { type OpenAPIV3, type Operation, type ParameterObject } from 'openapi-client-axios'
import { ArrayField, ArrayInput, AutocompleteArrayInput, BooleanField, BooleanInput, ChipField, DateField, DateInput, DateTimeInput, EmailField, NumberField, NumberInput, ReferenceArrayField, SelectField, SelectInput, SingleFieldList, TextField, TextInput, TimeInput, UrlField, type RaRecord } from 'react-admin'

import { ComponentType } from 'react'
import {
  email,
  maxLength,
  minLength,
  regex
} from 'react-admin'
import CreateSuggestionDialog from '../components/Dialog/CreateSuggestionDialog'
import GeoJsonField from '../components/Field/GeoJsonField'
import TruncatedTextField from '../components/Field/TruncatedTextField'
import GeoJsonInput from '../components/Input/GeoJsonInput'
import JsonApiReferenceField from './components/ReferenceField'
import SchemaAutocompleteInput from './components/SchemaAutocompleteInput'
import { buildChoices, getEncapsulatedSchema } from './openapi/parser'
import { type JsonApiDocument, type JsonApiPrimaryData, type ResourceIdentifierObject, type ResourceLinkage } from './types/jsonapi'

export interface FieldSchema {
  name: string
  reference?: string
  resource: string
  schema: OpenAPIV3.SchemaObject
  isRequired: boolean
  isReadOnly: boolean
  kind: 'attribute' | 'relationship' |'array-relationship'
}

export interface FieldDefinition {
  component: ComponentType<any>,
  props: {
    source: string
    [key: string]: any
  }
}


export const capsulateJsonApiPrimaryData = (data: RaRecord | Partial<any>, type: string, operation: Operation): JsonApiPrimaryData => {
  /** helper to transform react admin data to json:api conform primary data object
     *
     */
  const { id, ...attributes } = data
  const relationships: Record<string, ResourceLinkage> = {}

  const resourceSchema = getEncapsulatedSchema(operation)

  const jsonApiPrimaryDataProperties = resourceSchema?.properties as Record<string, OpenAPIV3.NonArraySchemaObject>
  const jsonApiResourceRelationships = jsonApiPrimaryDataProperties?.relationships?.properties as OpenAPIV3.NonArraySchemaObject
  for (const [relationName, resourceLinkageSchema] of Object.entries(jsonApiResourceRelationships ?? {})) {
    if (relationName in attributes) {
      // need to capsulate data of relationship as well
      const isList = Object.hasOwn(resourceLinkageSchema.properties.data, 'items')
      const relationSchema = isList ? resourceLinkageSchema?.properties?.data?.items as OpenAPIV3.NonArraySchemaObject : resourceLinkageSchema.properties.data as OpenAPIV3.NonArraySchemaObject
      const relationResourceType = relationSchema?.properties?.type as OpenAPIV3.NonArraySchemaObject

      if (isList) {
        const relationData: RaRecord[] = attributes[relationName]
        relationships[relationName] = { data: relationData.map((record: RaRecord) => ({ id: record.id, type: relationResourceType?.enum?.[0] })) }
      } else {
        const relationData: RaRecord = attributes[relationName]
        if (relationData !== undefined && relationData !== null) {
          relationships[relationName] = { data: { id: relationData.id, type: relationResourceType?.enum?.[0] } }
        }
      }
      // TODO: delete attributes.relationName does not work (no-dynamic-delete)
      delete attributes[relationName]  
    }
  }

  const primaryData: JsonApiPrimaryData = {
    id,
    type,
    attributes,
    ...(Object.keys(relationships).length > 0 && {relationships: relationships})
  }
  return primaryData
}

export const findIncludedData = (resourceIdentifierObject: ResourceIdentifierObject, document?: JsonApiDocument): JsonApiPrimaryData => {
  /** Searches for included object and returns it insted of the ResourceIdentifierObject */
  const founded = document?.included?.find((data: JsonApiPrimaryData) => data.id === resourceIdentifierObject.id && data.type === resourceIdentifierObject.type)
  const returnVal = founded ?? resourceIdentifierObject as JsonApiPrimaryData
  return returnVal
}

export const encapsulateJsonApiRelationship = (relationships: Record<string, ResourceLinkage>, allRecords: any, currentRecordId: string, preventCircular: boolean = false) => {
  for (const [relationName, resourceLinkage] of Object.entries(relationships || {})) {
    if (resourceLinkage.data === null) continue
    if (Array.isArray(resourceLinkage.data)) {
      const relatedObjects: any[] = []
      resourceLinkage.data.forEach(resourceIdentifierObject => {
        const linkedObjectId = `${resourceIdentifierObject.type}:${resourceIdentifierObject.id}`
        if (preventCircular) {
          relatedObjects.push({
            id: resourceIdentifierObject.id
          })
        } else {
          allRecords[linkedObjectId] = {
            id: resourceIdentifierObject.id,
            ...(linkedObjectId in allRecords && allRecords[linkedObjectId])
          }
          relatedObjects.push(allRecords[linkedObjectId])
        }
      })
      allRecords[currentRecordId][`${relationName}`] = relatedObjects
    } else {
      if (preventCircular){
        allRecords[currentRecordId][`${relationName}`] = {id: resourceLinkage.data.id}
      } else {
        const linkedObjectId = `${resourceLinkage.data.type}:${resourceLinkage.data.id}`
        allRecords[linkedObjectId] = {
          id: resourceLinkage.data.id,
          ...(linkedObjectId in allRecords && allRecords[linkedObjectId])
        }
        allRecords[currentRecordId][`${relationName}`] = allRecords[linkedObjectId]
      }
    }
  }

}

export const encapsulateJsonApiPrimaryData = (document: JsonApiDocument, data: JsonApiPrimaryData): RaRecord => {
  /** helper to transform json:api primary data object to react admin record
   *
   */

  const currentObjectId = `${data.type}:${data.id}`
  // lookup object for all resolved objects; doesn't matter if full described object of inclueded data or not
  const allRecords: any = {}
  allRecords[currentObjectId] = {
      id: data.id,
      ...data.attributes,
    }

  // encapsulate included data first
  document?.included?.forEach(primaryData => {
    const id = `${primaryData.type}:${primaryData.id}`
    allRecords[id] = {
      id: primaryData.id,
      ...primaryData.attributes,
       
    }
    encapsulateJsonApiRelationship(primaryData.relationships || {}, allRecords, id, true)
  })

  encapsulateJsonApiRelationship(data.relationships || {}, allRecords, currentObjectId)
  return allRecords[currentObjectId]
}

export const jsonApiToRaAdmin = (document: JsonApiDocument): RaRecord => {
  const includedMap: any = {}
  document?.included?.forEach(item => {
    includedMap[`${item.type}:${item.id}`] = item
  })

  const encapsulatedIncluded = {}

  return encapsulateJsonApiPrimaryData(document, document.data as JsonApiPrimaryData, encapsulatedIncluded) 
}

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
      const pattern = /\[(.*?)\]/;
      const resourceType = pattern.exec(parameterObject.name)?.[1]
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

export const hasIncludedData = (record: RaRecord): boolean => (Object.entries(record).find(([name, schema]) => name !== 'id') != null)


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
          kind: 'relationship'
        }
      }
        
    }
};

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

  if (forInput && nestedSchema.enum !== undefined && Array.isArray(nestedSchema.enum) && nestedSchema.enum.length > 0){
    // simple choice input
    definition.component = AutocompleteArrayInput;
    definition.props.choices = nestedSchema.enum.map(choice => ({id: choice, name: choice}));
  } else if (nestedSchema.type === 'object') {
    // TODO: nested resource
    // 1. get all nested fields of this object...
    // 2. create all nested fields...
    // 3. set children prop
    definition.component = forInput ? TextField: TextInput;
    console.debug(`nested resoruces are not supported for now. Source: ${source}`);
  } else {
    // single array of simple typed field
    if (!forInput){
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
      definition.component = forInput ? TextField: TextInput;

    }
  }
  return definition;
}

export const getFieldForFormat = (
  source: string, 
  schema: OpenAPIV3.SchemaObject, 
  isRequired: boolean = false, 
  isReadOnly: boolean = false, 
  forInput: boolean = true
): FieldDefinition => {
  const validate = [
    ... schema.maxLength ? [maxLength(schema.maxLength)] : [],
    ... schema.minLength ? [minLength(schema.minLength)] : [],
    ... schema.pattern ? [regex(new RegExp(schema.pattern))] : []
  ]

  const definition: FieldDefinition = {
      component: forInput ? TextInput: TextField,

      props: {
        source: source,
        label: schema.title ?? source,
        disabled: isReadOnly?? false,
        ...(schema.default && {defaultValue: schema.default}),
        ...(validate.length > 0 && {validate: validate}),
        ...(forInput && {required: isRequired}),
        ...(forInput && schema.description && {helperText: schema.description}),
        }
    }


  // See https://datatracker.ietf.org/doc/html/draft-bhutton-json-schema-validation-01#name-defined-formats for valid schema.format strings
  switch(schema.format){
    case 'date-time':
      definition.component = forInput ? DateTimeInput: DateField;
      definition.props.showTime = true;
      break;
    case 'date':
      definition.component = forInput ? DateInput: DateField;
      break;
    case 'time':
      definition.component = forInput ? TimeInput: DateField;
      definition.props.showTime = true;
      break;
    case 'duration':
      // TODO: is there a durationinput?
      // https://mui.com/x/react-date-pickers/
      definition.component = TextInput;
      break;
    case 'uri':
      definition.component = forInput ? TextInput: UrlField;
      definition.props.validate = [
        ...(definition.props.validate > 0 ? definition.props.validate: []),
        regex(/^(http(s?):\/\/.)[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)$/)
      ]
      break;
    case 'email':
      definition.component = forInput ? TextInput: EmailField;
      definition.props.validate = [
        ...(definition.props.validate > 0 ? definition.props.validate: []),
        email()
      ]
      break;
    case 'geojson':
      definition.component = forInput ? GeoJsonInput: GeoJsonField;
      break;
  }

  return definition;
}


export const getFieldForType = (
  source: string, 
  schema: OpenAPIV3.SchemaObject, 
  isRequired: boolean = false, 
  isReadOnly: boolean = false, 
  forInput: boolean = true): FieldDefinition => {
  
  const validate = [
    ... schema.maxLength ? [maxLength(schema.maxLength)] : [],
    ... schema.minLength ? [minLength(schema.minLength)] : [],
    ... schema.pattern ? [regex(new RegExp(schema.pattern))] : []
  ]

  const definition: FieldDefinition = {
      component: forInput ? TextInput: TextField,

      props: {
        source: source,
        label: schema.title ?? source,
        disabled: isReadOnly?? false,
        ...(schema.default && {defaultValue: schema.default}),
        ...(validate.length > 0 && {validate: validate}),
        ...(forInput && {required: isRequired}),
        ...(forInput && schema.description && {helperText: schema.description}),
        }
    }

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

export const getFieldDefinition = (api: OpenAPIClientAxios, fieldSchema: FieldSchema, forInput: boolean = true): FieldDefinition | undefined => {
  const commonProps = {
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
              create: <CreateSuggestionDialog isOpen resource={fieldSchema.reference}/>,
              createLabel: 'type something to create a new object', // TODO: use translate
              sort:{ field: 'name', order: 'ASC' }
            })
          }: 
          {
            reference: fieldSchema.reference, 
            target: fieldSchema.resource,
          })
      }
    }
    
  } else if (fieldSchema?.kind === 'array-relationship') {   
    const props = {
      ...commonProps,
      ...(forInput ? {multiple: true}: {reference: fieldSchema.reference, target: fieldSchema.resource,})
    }

    return {
      component: forInput ? SchemaAutocompleteInput: ReferenceArrayField, 
      props: {
        ...props,
        ...(props.defaultValue ?? {defaultValue: []}), // define an empty array as defaultValue. Otherwise it can results in to null values for this field as values, which causes TypeErrors on => undefined.map()
      }
    }
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
      const days = matches[1] ? parseInt(matches[1], 10) : 0; // Standardwert 0, wenn kein Tag vorhanden
      const hours = matches[2] ? parseInt(matches[2], 10) : 0; // Standardwert 0, wenn keine Stunde angegeben
      const minutes = matches[3] ? parseInt(matches[3], 10) : 0; // Standardwert 0, wenn keine Minuten angegeben
      const seconds = parseInt(matches[4], 10); // Sekunden sind immer da, daher keine Option
      const microseconds = parseInt(matches[5], 10); // Mikrosekunden sind immer da
  

      // Berechne die Gesamtzeit in Sekunden
      const totalSeconds = (days * 24 * 60 * 60) + (hours * 3600) + (minutes * 60) + seconds + (microseconds / 1000000);

      return Math.round(totalSeconds);
  } else {
      return 0
  }
}