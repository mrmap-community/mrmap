import { renderHook } from "@testing-library/react";
import { HttpMethod, type Operation } from "openapi-client-axios";
import { expect, it, vi } from "vitest";
import useResourceSchema from "./useResourceSchema";
const state = vi.hoisted(() => ({
  operation: undefined as Operation | undefined,
}));
vi.mock("../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({
    api: { getOperation: () => state.operation },
  }),
}));
vi.mock("../utils", () => ({
  getSortOptions: () => [],
  getSparseFieldOptionsPerResourceType: () => ({ Service: ["id"] }),
  getIncludeOptions: () => ["owner"],
}));
it("derives metadata on the same render and clears it for missing operations", () => {
  const schema = {
    type: "object" as const,
    properties: { id: { type: "string" as const } },
  };
  state.operation = {
    method: HttpMethod.Get,
    path: "/services",
    operationId: "list_Service",
    responses: {
      "200": {
        description: "",
        content: {
          "application/vnd.api+json": {
            schema: { properties: { data: { type: "array", items: schema } } },
          },
        },
      },
    },
  };
  const { result, rerender } = renderHook(
    ({ id }: { id: string | undefined }) => useResourceSchema(id),
    { initialProps: { id: "list_Service" as string | undefined } },
  );
  expect(result.current.schema).toBe(schema);
  expect(result.current.includeAbleResources).toEqual(["owner"]);
  rerender({ id: undefined });
  expect(result.current.schema).toBeUndefined();
  expect(result.current.includeAbleResources).toBeUndefined();
  expect(result.current.sortValues).toEqual([]);
});
