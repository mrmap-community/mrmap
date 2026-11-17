import type { JsonApiDocument, JsonApiPrimaryData } from "./types/jsonapi";

import { ArrayField, TextField, TextInput } from "react-admin";

import { describe, expect, it, vi } from "vitest";

import {
  encapsulateJsonApiDocumentData,
  encapsulateJsonApiPrimaryData,
  getArrayInput,
  getFieldForFormat,
  getFieldSchema,
  getIsoPath,
} from "./utils";
vi.mock("../components/Dialog/CreateSuggestionDialog", () => ({
  default: () => null,
}));
vi.mock("../components/Field/GeoJsonField", () => ({ default: () => null }));
vi.mock("../components/Input/GeoJsonInput", () => ({ default: () => null }));
vi.mock("./components/ReferenceField", () => ({ default: () => null }));
vi.mock("./components/ReferenceManyField", () => ({ default: () => null }));
vi.mock("./components/SchemaAutocompleteInput", () => ({
  default: () => null,
}));

const resources: JsonApiPrimaryData[] = [1, 2].map((id) => ({
  id,
  type: "Service",
  attributes: { title: `Service ${id}` },
  relationships: {
    owner: { data: { type: "User", id: 3 } },
    layers: { data: [{ type: "Layer", id: 4 }] },
    missing: { data: { type: "User", id: 99 } },
    nullable: { data: null },
  },
}));
const document: JsonApiDocument = {
  data: resources,
  included: [
    {
      type: "User",
      id: 3,
      attributes: { name: "Owner" },
      relationships: { service: { data: { type: "Service", id: 1 } } },
    },
    { type: "Layer", id: 4, attributes: { title: "Layer" } },
  ],
};
describe("JSON:API response conversion", () => {
  it("resolves included relationships and keeps nested cycles as id-only references", () => {
    const result = encapsulateJsonApiDocumentData(document, resources);
    expect(result[0]).toEqual({
      id: 1,
      title: "Service 1",
      owner: { id: 3, name: "Owner", service: { id: 1 } },
      layers: [{ id: 4, title: "Layer" }],
      missing: { id: 99 },
    });
    expect(result[1].title).toBe("Service 2");
    expect(() => JSON.stringify(result)).not.toThrow();
    expect(resources[0].attributes).toEqual({ title: "Service 1" });
  });
  it("normalizes included attributes once for an entire page", () => {
    const readAttributes = vi.fn(() => ({ name: "Owner" }));
    const included = {
      type: "User",
      id: 3,
      get attributes() {
        return readAttributes();
      },
    };
    encapsulateJsonApiDocumentData({ included: [included] }, resources);
    expect(readAttributes).toHaveBeenCalledTimes(1);
  });
  it("supports realtime records without a document and isolates primary records also present in included", () => {
    expect(
      encapsulateJsonApiPrimaryData(undefined, resources[0]).owner,
    ).toEqual({ id: 3 });
    const both = {
      ...document,
      included: [...document.included!, resources[0]],
    };
    const result = encapsulateJsonApiDocumentData(both, resources);
    expect(result[0].owner.name).toBe("Owner");
    expect(both.included[2].relationships?.owner.data).toEqual({
      type: "User",
      id: 3,
    });
  });
});


describe("formatted field validation", () => {
  it.each(["email", "uri"])("keeps length validation alongside %s validation", format => {
    const field = getFieldForFormat("address", { type: "string", format, minLength: 12 }, true);
    const validators = field.props.validate ?? [];
    expect(validators).toHaveLength(2);
    const validate = (value: string) => validators.map(validator => validator(value, {}, { source: "address" }));
    expect(validate(format === "email" ? "a@b.co" : "https://a.co").some(Boolean)).toBe(true);
    expect(validate("invalid-value").some(Boolean)).toBe(true);
    expect(validate(format === "email" ? "person@example.com" : "https://example.com").every(value => value === undefined)).toBe(true);
  });
});

/**
 * The array branches of the schema mapping chose display and input the other
 * way round than every other branch of the layer: a read-only field sat inside
 * a form and a raw input in a show screen (#1463).
 */
describe("array field mapping (#1463)", () => {
  const stringArray = { type: "array", items: { type: "string" } };
  const objectArray = { type: "array", items: { type: "object" } };

  it("asks for an input, not a read-out, for an array of strings in a form", () => {
    expect(
      getArrayInput("keywords", stringArray as never, false, false, true).component,
    ).toBe(TextInput);
  });

  it.each([
    { forInput: true, component: TextInput },
    { forInput: false, component: TextField },
  ])("maps the nested objects of an array the way the other branches do (forInput=$forInput)", ({ forInput, component }) => {
    // the branch names its missing support on the console; the spec is about
    // the component it chooses, not about that note
    const debug = vi.spyOn(console, "debug").mockImplementation(() => undefined);

    const field = getArrayInput("extent", objectArray as never, false, false, forInput);

    expect(field.component).toBe(component);
    debug.mockRestore();
  });

  it("keeps the chip list which displays an array of simple values", () => {
    const field = getArrayInput("keywords", stringArray as never, false, false, false);

    expect(field.component).toBe(ArrayField);
    expect(field.props.children).toBeDefined();
  });
});

describe("mapped element metadata (#1249)", () => {
  const schema = {
    properties: {
      attributes: {
        properties: {
          abstract: { type: "string", "x-iso-path": "identification.abstract" },
          title: { type: "string" },
        },
      },
      relationships: {
        properties: {
          metadataContact: {
            "x-iso-path": "contact.pointOfContact",
            properties: {
              data: { type: "object", properties: { type: { enum: ["Contact"] } } },
            },
          },
          owner: {
            properties: {
              data: { type: "object", properties: { type: { enum: ["User"] } } },
            },
          },
        },
      },
    },
  } as never;

  it("surfaces the x-iso-path extension on attributes and relationships", () => {
    expect(getFieldSchema("abstract", schema)?.isoPath).toBe(
      "identification.abstract",
    );
    expect(getFieldSchema("metadataContact", schema)?.isoPath).toBe(
      "contact.pointOfContact",
    );
    expect(getFieldSchema("metadataContact", schema)?.reference).toBe("Contact");
  });

  it("leaves fields without the extension unmapped", () => {
    expect(getFieldSchema("title", schema)?.isoPath).toBeUndefined();
    expect(getFieldSchema("owner", schema)?.isoPath).toBeUndefined();
  });

  it("only accepts a textual extension value", () => {
    expect(getIsoPath({ "x-iso-path": 42 } as never)).toBeUndefined();
    expect(getIsoPath(undefined)).toBeUndefined();
  });
});
