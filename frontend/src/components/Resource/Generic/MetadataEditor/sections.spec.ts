import type { FieldDefinition } from "../../../../jsonapi/utils";
import type { ProfileSection } from "./types";

import { describe, expect, it } from "vitest";

import {
  buildEditorSections,
  cardinalityFor,
  elementPathOf,
  flattenSectionFields,
  OTHER_SECTION_ID,
  sectionOfField,
} from "./sections";

const definition = (source: string, disabled = false): FieldDefinition => ({
  component: "input",
  props: { source, label: source, ...(disabled ? { disabled: true } : {}) },
});

const section = (
  id: string,
  fields: [string, ProfileSection["fields"][number]["requirement"]][],
): ProfileSection => ({
  id,
  label: id,
  fields: fields.map(([field, requirement]) => ({ field, requirement })),
});

const DEFINITIONS = [
  definition("title"),
  definition("abstract"),
  definition("lineStatement"),
  definition("keywords"),
  definition("dateType"),
  definition("origin", true),
  definition("id"),
];

const ISO_PATHS: Record<string, string> = {
  title: "/MD_Metadata/identificationInfo/MD_DataIdentification/citation/title",
  abstract:
    "/MD_Metadata/identificationInfo/MD_DataIdentification/abstract",
  lineStatement:
    "/MD_Metadata/identificationInfo/MD_DataIdentification/citation/alternateTitle",
};

const build = (mode: "simple" | "advanced") =>
  buildEditorSections({
    sections: [
      section("identification", [
        ["title", "mandatory"],
        ["abstract", "recommended"],
        ["lineStatement", "optional"],
        ["origin", "recommended"],
        ["notInTheSchema", "mandatory"],
      ]),
      // a section whose only field the schema does not expose disappears
      section("empty", [["missingField", "recommended"]]),
    ],
    definitions: DEFINITIONS,
    isoPaths: ISO_PATHS,
    repeatableSources: ["keywords"],
    mode,
    otherLabel: "Other elements",
  });

describe("cardinalityFor", () => {
  it("states the element cardinality from requirement and repeatable", () => {
    expect(cardinalityFor("mandatory", false)).toBe("1..1");
    expect(cardinalityFor("recommended", false)).toBe("0..1");
    expect(cardinalityFor("optional", true)).toBe("0..\u221e");
    expect(cardinalityFor("mandatory", true)).toBe("1..\u221e");
  });
});

describe("elementPathOf", () => {
  it("drops the leaf segment of an ISO path", () => {
    expect(elementPathOf("/a/b/c")).toBe("/a/b");
    expect(elementPathOf("/leaf")).toBeUndefined();
    expect(elementPathOf(undefined)).toBeUndefined();
  });
});

describe("buildEditorSections", () => {
  it("keeps mandatory and recommended fields in simple mode", () => {
    const sections = build("simple");
    expect(sections.map((s) => s.id)).toEqual(["identification"]);
    const sources = flattenSectionFields(sections[0]).map((f) => f.source);
    expect(sources).toEqual(["title", "abstract"]);
    expect(sections[0].mandatory).toEqual(["title"]);
  });

  it("adds optional section fields and the unnamed ones in advanced mode", () => {
    const sections = build("advanced");
    expect(sections.map((s) => s.id)).toEqual(["identification", OTHER_SECTION_ID]);
    const sources = flattenSectionFields(sections[0]).map((f) => f.source);
    expect(sources).toEqual(["title", "abstract", "lineStatement"]);
    const other = flattenSectionFields(sections[1]).map((f) => f.source);
    // unclaimed writable fields only: not the read-only origin, not the id
    expect(other).toEqual(["keywords", "dateType"]);
  });

  it("groups consecutive fields sharing one ISO element into one card", () => {
    const sections = build("advanced");
    const identification = sections[0].groups;
    // title and lineStatement cite the same citation element: they are not
    // consecutive here (abstract sits between), so each carries its own group
    expect(identification.map((g) => g.fields.map((f) => f.source))).toEqual([
      ["title"],
      ["abstract"],
      ["lineStatement"],
    ]);
    const titleGroup = identification[0];
    expect(titleGroup.cardinality).toBe("1..1");
    expect(titleGroup.elementPath).toBe(
      "/MD_Metadata/identificationInfo/MD_DataIdentification/citation",
    );
  });

  it("states a repeatable element with the infinity symbol", () => {
    const sections = build("advanced");
    const keywords = flattenSectionFields(sections[1]).find(
      (f) => f.source === "keywords",
    );
    expect(keywords?.cardinality).toBe("0..\u221e");
  });

  it("answers the section a field belongs to", () => {
    const sections = build("advanced");
    expect(sectionOfField(sections, "title")?.id).toBe("identification");
    expect(sectionOfField(sections, "keywords")?.id).toBe(OTHER_SECTION_ID);
    expect(sectionOfField(sections, "unknown")).toBeUndefined();
  });
});
