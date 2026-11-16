/**
 * Joining the profile's section data with the schema's writable fields (#1245).
 *
 * The profile answers which fields exist in which section and how strongly
 * they are required (#1240); the OpenAPI schema answers which of them the
 * record actually exposes, their labels, and — through the `x-iso-path`
 * extension — the ISO element each value is written into (#1240's schema
 * hook). Neither side is copied here: the builder only pairs them, so a new
 * profile (GDI-DE later) changes what the editor renders without changing
 * this file.
 *
 * Simple mode keeps the profile's mandatory and recommended fields;
 * Advanced mode additionally exposes the optional section fields and every
 * writable schema field no section names, and groups consecutive fields that
 * share one ISO element into a card whose chip states the element's
 * cardinality (1 for a mandatory element, 0 otherwise, ∞ for a repeatable
 * one — the reading the profile's own requirement flags give).
 */

import type { FieldDefinition } from "../../../../jsonapi/utils";

import {
  type EditorField,
  type EditorFieldGroup,
  type EditorMode,
  type EditorSection,
  type ProfileSection,
  type Requirement,
} from "./types";

/** the section Advanced mode appends for writable fields no section names */
export const OTHER_SECTION_ID = "other";

export const cardinalityFor = (
  requirement: Requirement,
  repeatable: boolean,
): string =>
  `${requirement === "mandatory" ? "1" : "0"}..${repeatable ? "\u221e" : "1"}`;

/** the ISO element a path writes into: the path without its leaf segment */
export const elementPathOf = (isoPath?: string): string | undefined => {
  if (!isoPath) return undefined;
  const cut = isoPath.lastIndexOf("/");
  return cut > 0 ? isoPath.slice(0, cut) : undefined;
};

const groupFields = (fields: EditorField[]): EditorFieldGroup[] => {
  const groups: EditorFieldGroup[] = [];
  for (const field of fields) {
    const last = groups.at(-1);
    if (last?.elementPath && last.elementPath === field.elementPath) {
      last.fields.push(field);
      continue;
    }
    groups.push({ elementPath: field.elementPath, fields: [field] });
  }
  // a group holds one ISO element: it is mandatory when any member is, and
  // repeatable when any member repeats — which the members' own cardinality
  // (built from the profile requirement and the schema's array-ness) states
  for (const group of groups) {
    if (!group.elementPath) continue;
    const mandatory = group.fields.some(
      (field) => field.requirement === "mandatory",
    );
    const repeatable = group.fields.some((field) =>
      field.cardinality?.endsWith("\u221e"),
    );
    group.cardinality = cardinalityFor(
      mandatory ? "mandatory" : "optional",
      repeatable,
    );
  }
  return groups;
};

export interface BuildSectionsInput {
  sections: ProfileSection[];
  definitions: FieldDefinition[];
  /** camelCase source -> x-iso-path of the OpenAPI property */
  isoPaths: Record<string, string>;
  /** sources the schema answers as an array (relationship or attribute) */
  repeatableSources: string[];
  mode: EditorMode;
  /** translated label of the Advanced-only "other" section */
  otherLabel: string;
}

/** one editor field: the profile's demand for a source, answered with the
 * schema's definition, ISO element and cardinality for this operation */
const editorField = (
  source: string,
  requirement: Requirement,
  definition: FieldDefinition,
  isoPaths: Record<string, string>,
  repeatableSources: string[],
): EditorField => {
  const isoPath = isoPaths[source];
  return {
    source,
    requirement,
    definition,
    isoPath,
    elementPath: elementPathOf(isoPath),
    cardinality: cardinalityFor(
      requirement,
      repeatableSources.includes(source),
    ),
  };
};

export const buildEditorSections = ({
  sections,
  definitions,
  isoPaths,
  repeatableSources,
  mode,
  otherLabel,
}: BuildSectionsInput): EditorSection[] => {
  const bySource = new Map(
    definitions.map((definition) => [definition.props.source, definition]),
  );
  const writable = (source: string): FieldDefinition | undefined => {
    const definition = bySource.get(source);
    // a read-only schema field is no editor field: its section entry has
    // nothing to write and the screen shows it in a read-only card instead
    if (!definition || definition.props.disabled) return undefined;
    return definition;
  };

  /** the sources a section claimed for itself: the advanced extras of the
   * same operation must not offer them a second time */
  const claimed = new Set<string>();

  /** the writable fields one profile section names, claiming its sources */
  const fieldsOfSection = (section: ProfileSection): EditorField[] => {
    const fields: EditorField[] = [];
    if (!Array.isArray(section?.fields)) return fields;
    for (const entry of section.fields) {
      if (typeof entry?.field !== "string" || !entry.field) continue;
      if (mode === "simple" && entry.requirement === "optional") continue;
      const definition = writable(entry.field);
      if (!definition) continue;
      claimed.add(entry.field);
      fields.push(
        editorField(
          entry.field,
          entry.requirement,
          definition,
          isoPaths,
          repeatableSources,
        ),
      );
    }
    return fields;
  };

  const built: EditorSection[] = [];
  for (const section of sections) {
    const fields = fieldsOfSection(section);
    // a section whose fields the schema does not expose (or the mode hides)
    // would render an empty card: it is no section of this record
    if (fields.length === 0) continue;
    built.push({
      id: section.id,
      label: section.label,
      groups: groupFields(fields),
      mandatory: fields
        .filter((field) => field.requirement === "mandatory")
        .map((field) => field.source),
    });
  }

  if (mode === "advanced") {
    const extras: EditorField[] = definitions
      .filter(
        (definition) =>
          !definition.props.disabled &&
          definition.props.source !== "id" &&
          !claimed.has(definition.props.source),
      )
      .map((definition) =>
        editorField(
          definition.props.source,
          "optional",
          definition,
          isoPaths,
          repeatableSources,
        ),
      );
    if (extras.length > 0) {
      built.push({
        id: OTHER_SECTION_ID,
        label: otherLabel,
        groups: groupFields(extras),
        mandatory: [],
      });
    }
  }
  return built;
};

/** the fields of a section in profile order, ignoring the ISO grouping */
export const flattenSectionFields = (section: EditorSection): EditorField[] =>
  section.groups.flatMap((group) => group.fields);

/** the section a field belongs to, for the rail badge and the jump-to-field */
export const sectionOfField = (
  sections: EditorSection[],
  source: string,
): EditorSection | undefined =>
  sections.find((section) =>
    flattenSectionFields(section).some((field) => field.source === source),
  );
