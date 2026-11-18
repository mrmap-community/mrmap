import { HttpMethod, type Operation } from "openapi-client-axios";
import { type OpenAPIV3 } from "openapi-types";
import { expect, it } from "vitest";

import { buildChoices, getRelatedResourceType, indexRelatedOperations } from "./parser";
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

// the contract during the #1487 migration: choices come from the
// x-enum-labels extension the backend emits (extras/schema.py), and the
// description prose is no input to the parser at all
it("builds choices from the x-enum-labels extension", () => {
  const property = {
    type: "integer",
    enum: [0, 1],
    description: "* `0` - Fatal\n* `1` - Error",
    "x-enum-labels": [
      { value: 0, label: "Fatal" },
      { value: 1, label: "Error" },
    ],
  } as never;
  expect(buildChoices(property)).toEqual([
    { id: 0, name: "Fatal" },
    { id: 1, name: "Error" },
  ]);
});

it("answers no choices when they are documented in prose only", () => {
  // defensive: before #1487 these choices were parsed out of the wording;
  // re-parsing it would silently reinstate the dependency on drf-spectacular
  const property: OpenAPIV3.SchemaObject = {
    type: "integer",
    enum: [0, 1],
    description: "* `0` - Fatal\n* `1` - Error",
  };
  expect(buildChoices(property)).toEqual([]);
});

it("keeps only the well-formed entries of the extension", () => {
  const property = {
    "x-enum-labels": [
      { value: "2", label: "Warning" }, // numeric string ids stay the contract
      { value: "eng", label: "English" }, // never a numeric id
      { value: 3 }, // no label
      null, // not an entry
      { value: 4.5, label: "Half" }, // not an integer id
    ],
  } as never;
  expect(buildChoices(property)).toEqual([{ id: 2, name: "Warning" }]);
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
