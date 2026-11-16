import type { Finding, ProfileRule } from "./types";

import { describe, expect, it } from "vitest";

import {
  clientFindings,
  completeness,
  isEmptyValue,
  mergeFindings,
  serverFindings,
  snakeToCamel,
} from "./rules";

const rule = (overrides: Partial<ProfileRule> = {}): ProfileRule => ({
  id: "R1",
  family: "identifiers",
  severity: "error",
  field: "title",
  assert: "normalize-space(.)",
  message: "A title is required.",
  ...overrides,
});

describe("snakeToCamel", () => {
  it("camelCases the model field names the rules carry", () => {
    expect(snakeToCamel("line_statement")).toBe("lineStatement");
    expect(snakeToCamel("date_type")).toBe("dateType");
    expect(snakeToCamel("title")).toBe("title");
    expect(snakeToCamel("two_word_field")).toBe("twoWordField");
  });
});

describe("isEmptyValue", () => {
  it("treats absent, blank and whitespace-only values as empty", () => {
    for (const value of [undefined, null, "", "   ", []]) {
      expect(isEmptyValue(value)).toBe(true);
    }
  });

  it("treats real values as filled", () => {
    for (const value of ["t", 0, false, 42, new Date(), { id: 3 }]) {
      expect(isEmptyValue(value)).toBe(false);
    }
  });

  it("treats an unusable number, date or id-less object as empty", () => {
    expect(isEmptyValue(NaN)).toBe(true);
    expect(isEmptyValue(new Date("nonsense"))).toBe(true);
    expect(isEmptyValue({ name: "no id yet" })).toBe(true);
    expect(isEmptyValue([null, ""])).toBe(true);
  });
});

describe("clientFindings", () => {
  it("reports a missing field the form carries", () => {
    expect(clientFindings([rule()], { title: "" })).toEqual([
      {
        key: "client:R1",
        ruleId: "R1",
        field: "title",
        severity: "error",
        detail: "A title is required.",
        family: "identifiers",
        origin: "client",
      },
    ]);
  });

  it("checks the camelCase name of a snake_case rule field", () => {
    const findings = clientFindings([rule({ field: "line_statement" })], {
      lineStatement: "   ",
    });
    expect(findings).toHaveLength(1);
    expect(findings[0].field).toBe("lineStatement");
  });

  it("keeps silent verdicts for what it cannot judge", () => {
    // a field the form never rendered has no client verdict
    expect(clientFindings([rule()], {})).toEqual([]);
    // a filled field passes
    expect(clientFindings([rule()], { title: "filled" })).toEqual([]);
    // a document-wide rule without a field is the server's to judge
    expect(clientFindings([rule({ field: null })], { title: "" })).toEqual([]);
    // no rules at all
    expect(clientFindings(undefined, { title: "" })).toEqual([]);
  });

  it("carries the rule's own severity through", () => {
    const findings = clientFindings([rule({ severity: "warning" })], {
      title: "",
    });
    expect(findings[0].severity).toBe("warning");
  });
});

describe("serverFindings", () => {
  it("reads the json:api error members #1243 defines", () => {
    const findings = serverFindings([
      {
        detail: "CI-0160: the resulting document lacks an extent.",
        source: { pointer: "/data/attributes/extent" },
        rule: "CI-0160",
        severity: "warning",
        meta: { family: "extents" },
      },
    ]);
    expect(findings).toEqual([
      {
        key: "server:0:CI-0160",
        ruleId: "CI-0160",
        field: "extent",
        severity: "warning",
        detail: "CI-0160: the resulting document lacks an extent.",
        family: "extents",
        origin: "server",
      },
    ]);
  });

  it("reads relationship pointers and keeps global findings unanchored", () => {
    const findings = serverFindings([
      { detail: "no contact", source: { pointer: "/data/relationships/metadataContact" }, rule: "R2" },
      { detail: "broken document", source: { pointer: "/data" } },
    ]);
    expect(findings[0].field).toBe("metadataContact");
    expect(findings[1].field).toBeUndefined();
    expect(findings[1].severity).toBe("error");
    expect(findings[1].key).toBe("server:1:/data");
    // rule-less findings still carry distinct keys
    expect(new Set(findings.map((f) => f.key)).size).toBe(2);
  });

  it("survives junk in the payload", () => {
    expect(serverFindings([null, 7, { detail: "x" }])).toHaveLength(1);
  });
});

describe("mergeFindings", () => {
  const finding = (overrides: Partial<Finding>): Finding => ({
    key: "k",
    severity: "error",
    detail: "d",
    origin: "client",
    ...overrides,
  });

  it("lets the server verdict win over the client copy of the same rule", () => {
    const merged = mergeFindings(
      [finding({ key: "client:R1", ruleId: "R1", detail: "client says" })],
      [finding({ key: "server:R1", ruleId: "R1", origin: "server", detail: "server says" })],
    );
    expect(merged).toHaveLength(1);
    expect(merged[0].origin).toBe("server");
  });

  it("keeps client findings the server did not answer and server findings without a rule", () => {
    const merged = mergeFindings(
      [finding({ key: "client:R1", ruleId: "R1" })],
      [finding({ key: "server:/data", origin: "server" })],
    );
    expect(merged).toHaveLength(2);
    expect(merged[0].origin).toBe("server");
  });
});

describe("completeness", () => {
  it("counts the mandatory fields the values fill", () => {
    expect(
      completeness(["title", "abstract"], { title: "t", abstract: "" }),
    ).toEqual({ filled: 1, total: 2 });
    expect(completeness([], {})).toEqual({ filled: 0, total: 0 });
  });
});
