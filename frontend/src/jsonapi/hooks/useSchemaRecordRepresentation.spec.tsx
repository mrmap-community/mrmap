import { renderHook } from "@testing-library/react";
import type { OpenAPIV3 } from "openapi-client-axios";
import { expect, it, vi } from "vitest";
import useSchemaRecordRepresentation from "./useSchemaRecordRepresentation";
const state = vi.hoisted(() => ({
  schema: undefined as OpenAPIV3.NonArraySchemaObject | undefined,
}));
vi.mock("react-admin", () => ({
  useResourceDefinition: () => ({ name: "Service" }),
}));
vi.mock("./useResourceSchema", () => ({
  default: () => ({ schema: state.schema }),
}));
it("uses schema field precedence and falls back when a schema disappears", () => {
  state.schema = {
    properties: {
      attributes: {
        properties: { stringRepresentation: {}, title: {}, name: {} },
      },
    },
  };
  const { result, rerender } = renderHook(() =>
    useSchemaRecordRepresentation({}),
  );
  const record = {
    id: 1,
    stringRepresentation: "Representation",
    title: "Title",
    name: "Name",
  };
  expect(result.current(record)).toBe("Representation");
  state.schema = {
    properties: { attributes: { properties: { title: {}, name: {} } } },
  };
  rerender();
  expect(result.current(record)).toBe("Title");
  state.schema = undefined;
  rerender();
  expect(result.current(record)).toBe("Service (1)");
});

it("returns a string when the schema uses a numeric ID", () => {
  state.schema = { properties: { attributes: { properties: {} } } };
  const { result } = renderHook(() => useSchemaRecordRepresentation({}));
  expect(result.current({ id: 20 })).toBe("20");
  expect(result.current({ id: 0 })).toBe("0");
});

it.each([null, undefined, {}])(
  "falls back for a missing or non-text label: %s",
  (value) => {
    state.schema = {
      properties: { attributes: { properties: { stringRepresentation: {} } } },
    };
    const { result } = renderHook(() => useSchemaRecordRepresentation({}));
    expect(result.current({ id: 20, stringRepresentation: value })).toBe(
      "Service (20)",
    );
  },
);
