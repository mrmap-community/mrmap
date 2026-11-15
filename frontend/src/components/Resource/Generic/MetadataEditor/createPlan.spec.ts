import { describe, expect, it } from "vitest";

import { parseProfileSections, planCreate } from "./createPlan";

// the shape seeded by registry migration 0049, trimmed to the decision points
const SECTIONS = [
  {
    id: "identification",
    label: "Identification",
    fields: [
      { field: "title", requirement: "mandatory" },
      { field: "abstract", requirement: "mandatory" },
      { field: "metadataContact", requirement: "mandatory" },
      { field: "categories", requirement: "recommended" },
    ],
  },
  {
    id: "extent",
    label: "Spatial and temporal extent",
    fields: [{ field: "boundingGeometry", requirement: "recommended" }],
  },
  {
    id: "quality",
    label: "Data quality",
    fields: [
      { field: "charset", requirement: "mandatory" },
      { field: "lineageStatement", requirement: "optional" },
    ],
  },
];

describe("parseProfileSections", () => {
  it("keeps the seeded shape as it is", () => {
    expect(parseProfileSections(SECTIONS)).toEqual(SECTIONS);
  });

  it("answers an empty plan for anything that is not a section list", () => {
    expect(parseProfileSections(undefined)).toEqual([]);
    expect(parseProfileSections("iso19139")).toEqual([]);
    expect(parseProfileSections({})).toEqual([]);
  });

  it("drops malformed entries instead of crashing the form", () => {
    const parsed = parseProfileSections([
      SECTIONS[0],
      null,
      { id: "no-label", fields: [] },
      { id: "no-fields", label: "No fields" },
      { id: "half", label: "Half", fields: [{ field: "title" }, { requirement: "mandatory" }, 7] },
    ]);
    expect(parsed).toEqual([
      SECTIONS[0],
      { id: "half", label: "Half", fields: [{ field: "title", requirement: "" }] },
    ]);
  });
});

describe("planCreate", () => {
  it("asks the mandatory fields the create operation allows to write, in profile order", () => {
    const plan = planCreate({ sections: SECTIONS, offered: ["profile", "title", "abstract", "charset", "categories"] });
    // metadataContact is mandatory but not offered here: not asked for
    expect(plan.askedFields).toEqual(["title", "abstract", "charset"]);
  });

  it("names the sections the asked fields give content, and the rest as later", () => {
    const plan = planCreate({ sections: SECTIONS, offered: ["profile", "title", "abstract", "charset"] });
    expect(plan.createdSections.map(section => section.id)).toEqual(["identification", "quality"]);
    expect(plan.laterSections.map(section => section.id)).toEqual(["extent"]);
  });

  it("counts a section as later when none of its fields is writable", () => {
    const plan = planCreate({ sections: SECTIONS, offered: ["profile"] });
    expect(plan.askedFields).toEqual([]);
    expect(plan.createdSections).toEqual([]);
    expect(plan.laterSections.map(section => section.id)).toEqual(["identification", "extent", "quality"]);
  });

  it("lists a field asked through two sections only once", () => {
    const doubled = [
      { id: "a", label: "A", fields: [{ field: "title", requirement: "mandatory" }] },
      { id: "b", label: "B", fields: [{ field: "title", requirement: "mandatory" }] },
    ];
    const plan = planCreate({ sections: doubled, offered: ["title"] });
    expect(plan.askedFields).toEqual(["title"]);
    expect(plan.createdSections.map(section => section.id)).toEqual(["a", "b"]);
  });

  it("recommends nothing into the form: only mandatory fields are asked", () => {
    const plan = planCreate({ sections: SECTIONS, offered: ["categories", "boundingGeometry", "lineageStatement"] });
    expect(plan.askedFields).toEqual([]);
  });
});
