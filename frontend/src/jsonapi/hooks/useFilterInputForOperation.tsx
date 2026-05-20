
import { type OpenAPIV3 } from 'openapi-client-axios';

import { AutocompleteInput, BooleanInput, NullableBooleanInput, NumberInput, TextInput, useResourceContext } from 'react-admin';
import GeoJsonInput from '../../components/Input/GeoJsonInput';
import SchemaAutocompleteInput from '../components/SchemaAutocompleteInput';
import { FieldDefinition } from '../utils';
import useOperation from './useOperation';


export const getFilterInputDefinitions = (schema: OpenAPIV3.ParameterObject, resource: string | undefined): FieldDefinition | undefined => {
  const filterExtensions = schema as OpenAPIV3.ParameterObject & Record<string, unknown>;
  
  const filterRelatedResourceType = filterExtensions['x-jsonapi-related-resource-type'] as string | undefined;
  const filterRelatedResourceField = filterExtensions['x-jsonapi-related-resource-field'] as string | undefined;
  const filterLookupExpression = filterExtensions['x-jsonapi-filter-lookup-expression'] as string | undefined;
  const filterLookupExpressionLabel = filterExtensions['x-jsonapi-filter-lookup-expression-label'] as string | undefined;
  
  const filterSchema = schema.schema as OpenAPIV3.SchemaObject;
  const name = schema.name.replace('filter[', '').replace(']', '').replace('.', '_filter_lookup_')
  
  var label = undefined

  switch(filterLookupExpression){
    case 'exact':
      label = filterExtensions?.['x-jsonapi-filter-label'] as string | undefined;
      break;
    case 'contains':
      label = `${filterRelatedResourceType}.${filterRelatedResourceField} ${filterLookupExpressionLabel}`
      break;
    case 'icontains':
      label = `${filterRelatedResourceType}.${filterRelatedResourceField} ${filterLookupExpressionLabel}`
      break;
    default:
      label = `${name} ${schema.description ? '(' + schema.description + ')': ''}`;
      break;
  }

  const commonProps = {
    source: name,
    isRequired: schema.required,
    label:  label,
    helperText: schema.description
  }

  if (filterRelatedResourceType && filterRelatedResourceField && filterLookupExpression == "exact"){
    const props = {
        ...commonProps,
        reference: filterRelatedResourceType,
        relatedResourceType: resource,
        multiple: false,
        parse: undefined, // resets the default behaviour to react-admins default
        format: undefined, // resets the default behaviour to react-admins default
    }
    return {
      component: SchemaAutocompleteInput,
      props: props
    }
  }

  // TODO: date, date-time, time, geojson
  else if (filterSchema.type === 'string'){
    if ((filterSchema.enum ?? []).length > 0) {
      return {
        component: AutocompleteInput,
        props: {
          ...commonProps,
          choices: filterSchema.enum?.map(value => ({id: value, name: value}))
        }
      }
    } else if (filterSchema.format === 'geojson') {
      return {component: GeoJsonInput, props: commonProps}
    } else {
      return {component: TextInput, props: commonProps}
    }
  } else if (filterSchema.type === 'integer'){
    return {
      component: NumberInput, 
      props: {
        ...commonProps, 
        min: filterSchema.minimum ?? '',
        max: filterSchema.maximum ?? '',
        defaultValue: filterSchema.default
      }
    }
  } else if (filterSchema.type === 'boolean'){
    return {
      component: schema.allowEmptyValue ? NullableBooleanInput: BooleanInput,
      props: {
        ...commonProps,

      }
    }
  }

};


export const useFilterInputForOperation = (
  operationId: string,
  orderMarker = 'order'
): FieldDefinition[] => {
  const operation = useOperation(operationId)
  const resource = useResourceContext()
  const parameters = operation?.parameters as OpenAPIV3.ParameterObject[]
  return parameters?.filter((parameter) => parameter.name.includes('filter['))
    .filter((filter) => !filter.name.includes(orderMarker))
    .map((parameter) => {
      return getFilterInputDefinitions(parameter, resource)
    }).filter(def => def !== undefined) ?? []
}