import type { JsonApiQueryParams, SparseFieldsets } from '../types/jsonapi';

import { useMemo } from 'react';
import { type ConfigurableDatagridColumn, useResourceDefinition, useStore } from 'react-admin';

import { snakeCase } from 'lodash';

import { getIncludeOptions } from '../utils';
import useSparseFieldsForOperation from './useSparseFieldsForOperation';

export interface UseJsonApiQueryProps {
  relatedResource?: string;
}

const useJsonApiQuery = ({ relatedResource }: UseJsonApiQueryProps) => {
  const { name, options } = useResourceDefinition();
  // Own useMemo: the `?? []` fallback of a schema without sparse fieldsets
  // would otherwise be a fresh array on every render and destabilise the
  // query memo below (and with it every consumer's request).
  const fieldsets = useMemo<SparseFieldsets[]>(() => options?.list?.sparseFieldsets ?? [], [options]);
  const operationId = relatedResource ? `list_related_${name}_of_${relatedResource}` : `list_${name}`;
  const { operation, sparseFields } = useSparseFieldsForOperation(operationId);
  const preferenceKey = `preferences.${operationId}.datagrid`;
  const [availableColumns] = useStore<ConfigurableDatagridColumn[]>(`${preferenceKey}.availableColumns`, []);
  const [omit] = useStore<string[]>(`${preferenceKey}.omit`, []);
  const [selectedColumnsIdxs] = useStore<string[]>(`${preferenceKey}.columns`, []);

  return useMemo(() => {
    const supported = new Set((sparseFields[name] ?? []).map(element => snakeCase(element)));
    const selected = availableColumns.filter(column =>
      column.source !== undefined && supported.has(snakeCase(column.source)) &&
      (selectedColumnsIdxs.length > 0 ? selectedColumnsIdxs.includes(column.index) : !omit.includes(column.source)),
    ).map(column => snakeCase(column.source));
    const query: JsonApiQueryParams = {};
    for (const fieldset of fieldsets) {
      query[`fields[${fieldset.type}]`] = fieldset.type === name
        ? [...new Set([...fieldset.fields.map(element => snakeCase(element)), ...selected])].join(',')
        : fieldset.fields.join(',');
    }
    // Wait until columns are registered; an empty fieldset would suppress default fields.
    if (!fieldsets.some(fieldset => fieldset.type === name) && selected.length > 0) {
      query[`fields[${name}]`] = selected.join(',');
    }
    query.include = (operation ? getIncludeOptions(operation) : [])
      .filter(include => selected.includes(snakeCase(include))).join(',');
    return query;
  }, [name, operation, sparseFields, fieldsets, availableColumns, omit, selectedColumnsIdxs]);
};

export default useJsonApiQuery;
