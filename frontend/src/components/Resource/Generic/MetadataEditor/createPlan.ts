/**
 * Derivation behind the blank-record wizard of issue #1248.
 *
 * The profile's `sections` JSON (#1240, seeded in registry migration 0049) is
 * the only source of what a record should carry: the wizard asks for the
 * profile's mandatory fields that the create operation actually allows to be
 * written, and the "what you get" panel names the sections which then start
 * with content and the ones Advanced mode fills later. Pure functions so both
 * halves are testable without a form or a schema.
 */

export interface ProfileSectionField {
  field: string;
  requirement: string;
}

export interface ProfileSection {
  id: string;
  label: string;
  fields: ProfileSectionField[];
}

/**
 * The `sections` attribute arrives as free JSON from the profile resource;
 * anything not shaped like a section is dropped instead of crashing the form.
 */
export const parseProfileSections = (sections: unknown): ProfileSection[] => {
  if (!Array.isArray(sections)) return [];
  return sections.flatMap(section => {
    if (typeof section !== "object" || section === null) return [];
    const { id, label, fields } = section as Partial<ProfileSection>;
    if (typeof id !== "string" || typeof label !== "string" || !Array.isArray(fields)) return [];
    const parsedFields = fields.flatMap(field => {
      if (typeof field !== "object" || field === null) return [];
      const { field: name, requirement } = field as Partial<ProfileSectionField>;
      if (typeof name !== "string") return [];
      return [{ field: name, requirement: typeof requirement === "string" ? requirement : "" }];
    });
    return [{ id, label, fields: parsedFields }];
  });
};

export interface CreatePlan {
  /**
   * The sources the create form asks for from the profile's mandatory set —
   * in profile order, and only those the create operation allows to write.
   */
  askedFields: string[];
  /** Sections that start with content, because the form asks for one of their fields. */
  createdSections: ProfileSection[];
  /** Sections the record only gains in Advanced mode (#1245). */
  laterSections: ProfileSection[];
}

/**
 * `offered` is the writable field sources of the record's create operation;
 * a mandatory field the API does not let a creator write cannot be asked for,
 * and its section then honestly counts as "added later".
 */
export const planCreate = ({ sections, offered }: {
  sections: ProfileSection[];
  offered: string[];
}): CreatePlan => {
  const askedFields = sections
    .flatMap(section => section.fields)
    .filter(field => field.requirement === "mandatory" && offered.includes(field.field))
    .map(field => field.field)
    .filter((name, index, all) => all.indexOf(name) === index);
  const asked = new Set(askedFields);
  const isCreated = (section: ProfileSection) => section.fields.some(field => asked.has(field.field));
  return {
    askedFields,
    createdSections: sections.filter(isCreated),
    laterSections: sections.filter(section => !isCreated(section)),
  };
};
