import { HttpMethod, type Operation } from "openapi-client-axios";
import { type OpenAPIV3 } from "openapi-types";
import { expect, it } from "vitest";

import { getRelatedResourceType, indexRelatedOperations } from "./parser";
const operation = (operationId: string): Operation => ({
  operationId,
  method: HttpMethod.Get,
  path: "/",
  responses: {},
});
it("indexes related operations in order without matching resource-name prefixes", () => {
  const first = operation("list_related_Layer_of_WebMapService");
  const second = operation("list_related_Probe_of_WebMapService");
  const other = operation("list_related_Run_of_WebMapServiceMonitoringSetting");
  const index = indexRelatedOperations([
    first,
    operation("list_WebMapService"),
    other,
    second,
  ]);
  expect(index.get("WebMapService")).toEqual([first, second]);
  expect(index.get("WebMapServiceMonitoringSetting")).toEqual([other]);
  expect(index.size).toBe(2);
});

/** the 200 answer of a nested list: a data array whose items name their JSON:API type */
const nestedListOperation = (resourceType: string): Operation => {
  const schema: OpenAPIV3.SchemaObject = {
    type: "object",
    properties: {
      data: {
        type: "array",
        items: {
          type: "object",
          properties: { type: { allOf: [{ enum: [resourceType] }] } },
        },
      },
    },
  };
  return {
    operationId: `list_related_${resourceType}_of_WebMapService`,
    method: HttpMethod.Get,
    path: "/",
    responses: {
      "200": { description: "", content: { "application/vnd.api+json": { schema } } },
    },
  };
};

it("reads the JSON:API type of the records a nested list answers with", () => {
  expect(getRelatedResourceType(nestedListOperation("Layer"))).toBe("Layer");
});

it("answers no type for an operation that names none", () => {
  expect(
    getRelatedResourceType(operation("list_related_Layer_of_WebMapService")),
  ).toBeUndefined();
});
