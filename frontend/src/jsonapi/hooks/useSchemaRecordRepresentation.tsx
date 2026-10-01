import { useCallback } from "react";
import {
  type RaRecord,
  RecordToStringFunction,
  useResourceDefinition,
} from "react-admin";

import { type OpenAPIV3 } from "openapi-client-axios";

import useResourceSchema from "./useResourceSchema";

export interface SchemaRecordRepresentationProps {
  operationId?: string;
  resource?: string;
}

const getRecordRepresentationFromSchema = (
  schema: OpenAPIV3.NonArraySchemaObject,
): string => {
  const attributes = (
    schema.properties?.attributes as OpenAPIV3.SchemaObject | undefined
  )?.properties;
  return (
    ["stringRepresentation", "title", "name"].find(
      (field) => attributes !== undefined && Object.hasOwn(attributes, field),
    ) ?? "id"
  );
};

const useSchemaRecordRepresentation = ({
  operationId,
  resource,
}: SchemaRecordRepresentationProps): RecordToStringFunction => {
  const { name } = useResourceDefinition({ resource: resource });
  const { schema } = useResourceSchema(operationId ?? `list_${name}`);

  const representation = schema
    ? getRecordRepresentationFromSchema(schema)
    : undefined;

  const optionTextFunc = useCallback(
    (record: RaRecord) => {
      if (representation !== undefined) {
        return Object.hasOwn(record, representation)
          ? record[representation]
          : `${name} (${record.id})`;
      } else {
        return `${name} (${record.id})`;
      }
    },
    [representation, name],
  );

  return optionTextFunc;
};

export default useSchemaRecordRepresentation;
