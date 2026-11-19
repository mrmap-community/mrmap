import { useMemo } from "react";
import { useResourceDefinition } from "react-admin";

import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import useResourceSchema from "../../../../jsonapi/hooks/useResourceSchema";
import { FieldDefinition, getFieldSchema } from "../../../../jsonapi/utils";

/**
 * One element a batch edit may change over the selected records.
 *
 * The candidates are the fields of the record's PATCH operation which the
 * schema carries with an `x-iso-path` (#1240): the write mapper reads the
 * same path, so an element offered here is exactly an element whose value
 * reaches the ISO document through the ordinary save path (#1242) - there
 * is no second mapping this screen could drift from.
 */
export interface MappedElement {
  source: string;
  label: string;
  isoPath: string;
  kind: "attribute" | "relationship" | "array-relationship";
  reference?: string;
  /** The schema-driven input definition of the field, reused for the value editor. */
  definition: FieldDefinition;
}

/** The writable mapped elements of one metadata record resource (#1249). */
const useMappedElements = (resource?: string): MappedElement[] => {
  const { name } = useResourceDefinition({ resource });
  const operationId = `partial_update_${name}`;
  const { schema } = useResourceSchema(operationId);
  const definitions = useFieldsForOperation({ operationId });

  return useMemo(() => {
    if (schema === undefined) return [];
    return definitions
      .map((definition): MappedElement | undefined => {
        const source = definition.props.source;
        if (source === undefined || source === "id") return undefined;
        const fieldSchema = getFieldSchema(source, schema);
        if (
          fieldSchema === undefined ||
          fieldSchema.isReadOnly ||
          fieldSchema.isoPath === undefined
        ) {
          return undefined;
        }
        return {
          source,
          label: definition.props.label ?? source,
          isoPath: fieldSchema.isoPath,
          kind: fieldSchema.kind,
          reference: fieldSchema.reference,
          definition,
        } satisfies MappedElement;
      })
      .filter((element): element is MappedElement => element !== undefined);
  }, [definitions, schema]);
};

export default useMappedElements;
