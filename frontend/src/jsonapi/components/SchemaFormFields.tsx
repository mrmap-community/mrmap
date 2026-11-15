import type { FieldDefinition } from '../utils';

import { createElement } from 'react';
import type { RaRecord } from 'react-admin';

import { useFieldsForOperation } from '../hooks/useFieldsForOperation';

export default function SchemaFormFields({ operationId, overrides, record, omit = [], only = undefined }: {
  operationId: string;
  overrides?: FieldDefinition[];
  record?: RaRecord;
  omit?: string[];
  /**
   * The sources to ask for, when the screen renders a subset of the operation's
   * fields instead of all of them — the create wizard of a metadata record asks
   * only what its profile makes mandatory (#1248). Read-only fields stay
   * filtered out: `only` narrows the form, it never offers a member the schema
   * pins as not writable.
   */
  only?: string[];
}) {
  const definitions = useFieldsForOperation({ operationId });
  // Preserve the form's shallow prop overrides and schema-disabled filtering.
  return definitions.filter(definition => !definition.props.disabled && !omit.includes(definition.props.source)
    && (only === undefined || only.includes(definition.props.source))).map(definition => {
    const override = overrides?.find(item => item.props.source === definition.props.source);
    return createElement(override?.component ?? definition.component, {
      ...definition.props,
      key: `${definition.props.source}-${record?.id ?? ''}`,
      ...(record && { record }),
      ...override?.props,
    });
  });
}
