import type { FieldDefinition } from "../../../../jsonapi/utils";

import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";
import useMappedElements from "./useMappedElements";

vi.mock("react-admin", () => ({
  useResourceDefinition: () => ({ name: "DatasetMetadataRecord" }),
}));
vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: vi.fn(),
}));
vi.mock("../../../../jsonapi/hooks/useResourceSchema", () => ({
  default: () => ({ schema: state.schema }),
}));

const state = vi.hoisted(() => ({
  schema: undefined as object | undefined,
}));

const field = (source: string): FieldDefinition => ({
  component: () => null,
  props: { source, label: source },
});

beforeEach(() => {
  state.schema = {
    properties: {
      attributes: {
        properties: {
          abstract: { type: "string", "x-iso-path": "identification.abstract" },
          title: { type: "string" },
          dateStamp: {
            type: "string",
            readOnly: true,
            "x-iso-path": "dateStamp",
          },
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
  vi.mocked(useFieldsForOperation).mockReturnValue([
    field("title"),
    field("abstract"),
    field("dateStamp"),
    field("metadataContact"),
    field("owner"),
    field("recordUuid"),
  ]);
});

describe("useMappedElements", () => {
  it("offers exactly the writable fields carrying an x-iso-path", () => {
    const { result } = renderHook(() => useMappedElements("DatasetMetadataRecord"));
    expect(result.current.map((item) => item.source)).toEqual([
      "abstract",
      "metadataContact",
    ]);
    const [abstract, contact] = result.current;
    expect(abstract).toMatchObject({
      isoPath: "identification.abstract",
      kind: "attribute",
    });
    expect(contact).toMatchObject({
      isoPath: "contact.pointOfContact",
      kind: "relationship",
      reference: "Contact",
    });
    // the value editor reuses the schema-driven input of the field itself
    expect(abstract.definition.props.source).toBe("abstract");
  });

  it("is empty while the patch schema is not available", () => {
    state.schema = undefined;
    const { result } = renderHook(() => useMappedElements("DatasetMetadataRecord"));
    expect(result.current).toEqual([]);
  });

  it("ignores fields the patch schema does not describe", () => {
    const { result } = renderHook(() => useMappedElements("DatasetMetadataRecord"));
    expect(result.current.some((item) => item.source === "recordUuid")).toBe(false);
  });
});
