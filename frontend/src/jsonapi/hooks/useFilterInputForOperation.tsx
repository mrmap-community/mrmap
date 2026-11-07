
import { AutocompleteInput, BooleanInput, NullableBooleanInput, NumberInput, TextInput, useResourceContext, useTranslate, type TranslateFunction } from 'react-admin';

import { type OpenAPIV3 } from 'openapi-client-axios';

import GeoJsonInput from '../../components/Input/GeoJsonInput';
import SchemaAutocompleteInput from '../components/SchemaAutocompleteInput';
import { FieldDefinition } from '../utils';
import useOperation from './useOperation';


export const humaniseFilterName = (name: string): string => {
  // Renders a raw filter name as readable words: "bbox_lat_lon__intersects" becomes
  // "Bbox lat lon intersects". Used whenever the schema has no human label for the
  // filter, so an unlabeled field degrades to readable text, never to "(undefined)" (#945).
  const words = name
    .replaceAll('_filter_lookup_', ' ') // the source mangled relation path separators; undo it for the label
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .split(/[^A-Za-z0-9]+/)
    .filter((word) => word.length > 0);
  if (words.length === 0) {
    return name;
  }
  const [first, ...rest] = words;
  return [first.charAt(0).toUpperCase() + first.slice(1), ...rest].join(' ');
};

export const getFilterInputDefinitions = (schema: OpenAPIV3.ParameterObject, resource: string | undefined, translate?: TranslateFunction): FieldDefinition | undefined => {
  const filterExtensions = schema as OpenAPIV3.ParameterObject & Record<string, unknown>;
  
  const filterRelatedResourceType = filterExtensions['x-jsonapi-related-resource-type'] as string | undefined;
  const filterRelatedResourceField = filterExtensions['x-jsonapi-related-resource-field'] as string | undefined;
  const filterLookupExpression = filterExtensions['x-jsonapi-filter-lookup-expression'] as string | undefined;
  const filterLookupExpressionLabel = filterExtensions['x-jsonapi-filter-lookup-expression-label'] as string | undefined;
  const filterFieldParts = filterExtensions['x-jsonapi-field-parts'] as string[] | undefined;

  const filterSchema = schema.schema as OpenAPIV3.SchemaObject;
  const name = schema.name
  .replaceAll('filter[', '')
  .replaceAll(']', '')
  .replaceAll('.', '_filter_lookup_');

  // the operation suffix the schema documents for this filter; the extension is
  // English-only, a parameter without any of both is one the backend could not
  // label (#945), so its option label is completed by the fallback below
  const operationLabel = filterLookupExpressionLabel ?? (schema.description !== undefined && schema.description !== '' ? `(${schema.description})` : '');
  const fallbackLabel = [filterFieldParts?.join('.') ?? humaniseFilterName(name), operationLabel].filter(Boolean).join(' ');
  // react-admin would resolve this string as a translation key with the key
  // itself as fallback, which would print raw names for every filter the
  // translations do not know; resolving it here lets the `filterFields`
  // translations (en + de) win while unknown fields stay readable
  const label = operationLabel === '' && translate !== undefined
    ? translate(`filterFields.${name}`, { _: fallbackLabel })
    : fallbackLabel;

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
  } else if (filterRelatedResourceType && filterRelatedResourceField && filterLookupExpression == "in"){
    const props = {
        ...commonProps,
        reference: filterRelatedResourceType,
        relatedResourceType: resource,
        multiple: true,
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
  const translate = useTranslate()
  const parameters = operation?.parameters as OpenAPIV3.ParameterObject[]
  return parameters?.filter((parameter) => parameter.name.includes('filter['))
    .filter((filter) => !filter.name.includes(orderMarker))
    .map((parameter) => {
      return getFilterInputDefinitions(parameter, resource, translate)
    }).filter(def => def !== undefined) ?? []
}