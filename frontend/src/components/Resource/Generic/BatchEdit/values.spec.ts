import type { MappedElement } from "./useMappedElements";

import { describe, expect, it } from "vitest";

import { isSameValue, relatedIds, serializerFieldName } from "./values";

const element = (kind: MappedElement["kind"]): MappedElement =>
  ({ source: "x", label: "X", isoPath: "p", kind }) as MappedElement;

describe("serializerFieldName", () => {
  it.each([
    ["abstract", "abstract"],
    ["metadataContact", "metadata_contact"],
    ["dateStamp", "date_stamp"],
  ])("names %s as the serializer does", (source, expected) => {
    expect(serializerFieldName(source)).toBe(expected);
  });
});

describe("relatedIds", () => {
  it("reads the ids a relationship value stands for", () => {
    expect(relatedIds({ id: "a" })).toEqual(["a"]);
    expect(relatedIds([{ id: "a" }, { id: "b" }])).toEqual(["a", "b"]);
  });

  it("is empty for values without a related record", () => {
    expect(relatedIds(undefined)).toEqual([]);
    expect(relatedIds(null)).toEqual([]);
    expect(relatedIds("scalar")).toEqual([]);
    expect(relatedIds([{ id: "a" }, null])).toEqual(["a"]);
  });
});

describe("isSameValue", () => {
  it("compares attributes by value, treating missing as empty", () => {
    expect(isSameValue(element("attribute"), "a", "a")).toBe(true);
    expect(isSameValue(element("attribute"), false, false)).toBe(true);
    expect(isSameValue(element("attribute"), "a", "b")).toBe(false);
    expect(isSameValue(element("attribute"), undefined, null)).toBe(true);
    expect(isSameValue(element("attribute"), undefined, "x")).toBe(false);
  });

  it("compares relationships by related id, order independent", () => {
    const reference = element("relationship");
    expect(isSameValue(reference, { id: "a" }, { id: "a" })).toBe(true);
    expect(isSameValue(reference, { id: "a" }, { id: "b" })).toBe(false);
    expect(isSameValue(reference, undefined, { id: "a" })).toBe(false);
    expect(
      isSameValue(
        element("array-relationship"),
        [{ id: "a" }, { id: "b" }],
        [{ id: "b" }, { id: "a" }],
      ),
    ).toBe(true);
    expect(
      isSameValue(element("array-relationship"), [{ id: "a" }], { id: "a" }),
    ).toBe(true);
    expect(
      isSameValue(element("array-relationship"), [{ id: "a" }], []),
    ).toBe(false);
  });
});
