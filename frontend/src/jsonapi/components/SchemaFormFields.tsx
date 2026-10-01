import { createElement } from 'react';
import type { RaRecord } from 'react-admin';
import { useFieldsForOperation } from '../hooks/useFieldsForOperation';
import type { FieldDefinition } from '../utils';

export default function SchemaFormFields({ operationId, overrides, record }: {
  operationId: string;
  overrides?: FieldDefinition[];
  record?: RaRecord;
}) {
  const definitions = useFieldsForOperation({ operationId });
  // Preserve the form's shallow prop overrides and schema-disabled filtering.
  return definitions.filter(definition => !definition.props.disabled).map(definition => {
    const override = overrides?.find(item => item.props.source === definition.props.source);
    return createElement(override?.component ?? definition.component, {
      ...definition.props,
      key: `${definition.props.source}-${record?.id ?? ''}`,
      ...(record && { record }),
      ...override?.props,
    });
  });
}
