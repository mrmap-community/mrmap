import { HttpMethod, type Operation } from "openapi-client-axios";
import { expect, it } from "vitest";
import { indexRelatedOperations } from "./parser";
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
