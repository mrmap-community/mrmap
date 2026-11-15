import type { MappedElement } from "./useMappedElements";

import type { Identifier } from "react-admin";

import { isEqual } from "lodash";

/** The serializer-side spelling of a served field name: sparse fieldsets and
 *  includes are named as the serializer names them, the schema answers them
 *  camelCased (#1080: what a screen sends is an api contract). */
export const serializerFieldName = (source: string): string =>
  source.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);

/** The related identifiers a relationship value stands for - compared for
 *  "already set" instead of any display text. */
export const relatedIds = (value: unknown): Identifier[] => {
  const items = Array.isArray(value) ? value : [value];
  return items
    .filter(
      (item): item is { id: Identifier } =>
        item != null && typeof item === "object" && "id" in item,
    )
    .map((item) => item.id);
};

/** Whether a record already carries the value the batch would write - such a
 *  record is skipped: an ordinary PATCH of an unchanged value is an empty
 *  document patch the endpoint refuses, and work nobody asked for. */
export const isSameValue = (
  element: MappedElement,
  current: unknown,
  next: unknown,
): boolean =>
  element.kind === "attribute"
    ? isEqual(current ?? null, next ?? null)
    : isEqual(relatedIds(current).map(String).sort(), relatedIds(next).map(String).sort());
