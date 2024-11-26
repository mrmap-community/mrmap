
import { type OpenAPIV3 } from 'openapi-client-axios';

import { AutocompleteInput, BooleanInput, NullableBooleanInput, NumberInput, TextInput } from 'react-admin';
import GeoJsonInput from '../../components/Input/GeoJsonInput';
import { FieldDefinition } from '../utils';
import useOperation from './useOperation';


export const getFilterInputDefinitions = (schema: OpenAPIV3.ParameterObject): FieldDefinition | undefined => {
  const filterSchema = schema.schema as OpenAPIV3.SchemaObject;
  const name = schema.name.replace('filter[', '').replace(']', '').replace('.', '_filter_lookup_')

  const commonProps = {
    source: name,
    isRequired: schema.required,
    label:  `${name} ${schema.description ? '(' + schema.description + ')': ''}`,
    helperText: schema.description
  }
  // TODO: date, date-time, time, geojson
  if (filterSchema.type === 'string'){
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

  const parameters = operation?.parameters as OpenAPIV3.ParameterObject[]
  return parameters?.filter((parameter) => parameter.name.includes('filter['))
    .filter((filter) => !filter.name.includes(orderMarker))
    .map((parameter) => {
      return getFilterInputDefinitions(parameter)
    }).filter(def => def !== undefined) ?? []
}