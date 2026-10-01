import { useMemo } from "react";

import { type OpenAPIV3, type Operation } from "openapi-client-axios";

import { SortPayload } from "react-admin";
import { getEncapsulatedSchema } from "../openapi/parser";
import {
  getIncludeOptions,
  getSortOptions,
  getSparseFieldOptionsPerResourceType,
} from "../utils";
import useOperation from "./useOperation";

export interface OperationSchema {
  schema?: OpenAPIV3.NonArraySchemaObject;
  operation?: Operation;
  sortValues?: SortPayload[];
  sparseFieldsPerResource?: { [key: string]: string[] };
  includeAbleResources?: string[];
}

const useResourceSchema = (
  operationId: string | undefined,
): OperationSchema => {
  const operation = useOperation(operationId);
  return useMemo(
    () => ({
      operation,
      schema: operation ? getEncapsulatedSchema(operation) : undefined,
      sortValues: operation ? getSortOptions(operation) : [],
      sparseFieldsPerResource: operation
        ? getSparseFieldOptionsPerResourceType(operation)
        : undefined,
      includeAbleResources: operation
        ? getIncludeOptions(operation)
        : undefined,
    }),
    [operation],
  );
};

export default useResourceSchema;
