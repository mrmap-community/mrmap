/** the readable text of one feature property: objects and null render as JSON, the rest as-is */
export const propertyText = (value: unknown): string => {
  const property = value as string | number | boolean | null | undefined | object;
  if (property === undefined) return "";
  if (property === null || typeof property === "object") return JSON.stringify(property);
  if (typeof property === "string") return property;
  return String(property);
};
