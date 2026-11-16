/**
 * Types of the full screen record editor (#1245).
 *
 * The shapes mirror what the api serves rather than a second frontend model:
 * `sections` and `rules` are the plain JSON attributes of the metadata
 * profile resource (#1240 seeds them, #1243 defines the rule shape in
 * `registry/mappers/rules.py`), and every finding names the rule id the
 * server cites so the rail can match its own pre-validation against the
 * json:api error payload of a refused save.
 */

import type { FieldDefinition } from "../../../../jsonapi/utils";

export type Requirement = "mandatory" | "recommended" | "optional";

export type EditorMode = "simple" | "advanced";

/** One field entry of a profile section, as the profile row carries it. */
export interface ProfileSectionField {
  field: string;
  requirement: Requirement;
}

/** One section of the profile: the grouping the editor's rail renders. */
export interface ProfileSection {
  id: string;
  label: string;
  fields: ProfileSectionField[];
}

/**
 * One ISO structural rule of the profile (#1243's rule shape). The `assert`
 * is an XPath over the resulting ISO document, which only the server can
 * build; the client pre-validates the rule's `field` against the form values.
 */
export interface ProfileRule {
  id: string;
  family: string;
  severity: "error" | "warning";
  field?: string | null;
  assert: string;
  message: string;
}

/** The `profile` relationship of the record, as `include=profile` answers it. */
export interface ProfileData {
  id?: string;
  name?: string;
  label?: string;
  sections?: ProfileSection[];
  rules?: ProfileRule[];
}

export type FindingSeverity = "error" | "warning";

/**
 * One line of the findings rail. Client findings come from the profile rules
 * evaluated against the current form values, server findings from the
 * json:api errors of a refused save; `ruleId` is what matches the two.
 */
export interface Finding {
  key: string;
  ruleId?: string;
  /** the record field the finding points at, camelCased like the form */
  field?: string;
  severity: FindingSeverity;
  detail: string;
  family?: string;
  origin: "client" | "server";
}

/** A writable field placed into a section, ready to render. */
export interface EditorField {
  source: string;
  requirement: Requirement;
  definition: FieldDefinition;
  isoPath?: string;
  /** the ISO element this field is written into (x-iso-path minus its leaf) */
  elementPath?: string;
  cardinality?: string;
}

/** Consecutive fields sharing one ISO element, grouped in Advanced mode. */
export interface EditorFieldGroup {
  elementPath?: string;
  cardinality?: string;
  fields: EditorField[];
}

/** A section of the editor: profile data joined with the schema fields. */
export interface EditorSection {
  id: string;
  label: string;
  groups: EditorFieldGroup[];
  mandatory: string[];
}
