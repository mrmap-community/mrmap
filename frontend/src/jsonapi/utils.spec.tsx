import { describe, expect, it, vi } from "vitest";
import {
  encapsulateJsonApiDocumentData,
  encapsulateJsonApiPrimaryData,
} from "./utils";
import type { JsonApiDocument, JsonApiPrimaryData } from "./types/jsonapi";
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
