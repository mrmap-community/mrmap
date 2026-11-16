/**
 * The client side of the profile rules (#1245).
 *
 * The rules travel on the profile resource with the record
 * (`include=profile`, Q1 option C on #1243). Their `assert` is an XPath over
 * the RESULTING ISO document — the stored document with the patched values
 * written through the write mapper (#1242) — which only the server can
 * build. The client therefore pre-validates what it honestly knows: the
 * presence of the rule's `field` in the values a save would send. Every
 * seeded v1 rule is such a presence rule over an editable or read-only
 * field, so the rail states the finding before the curator attempts the
 * save; the server keeps the authority over the document and refuses the
 * same rule id on a write (fail-closed), and `mergeFindings` makes the two
 * verdicts agree by that id.
 */

import type { Finding, ProfileRule } from "./types";

/** drf-jsonapi answers model fields camelCased; the rules name the model. */
export const snakeToCamel = (name: string): string =>
  name.replace(/_([a-z0-9])/g, (_match, letter: string) =>
    letter.toUpperCase(),
  );

/**
 * Whether a form value carries nothing the ISO document could keep: no
 * scalar, no text but whitespace, no related instance. A selected contact
 * object without an id is no contact.
 */
export const isEmptyValue = (value: unknown): boolean => {
  if (value === undefined || value === null) return true;
  if (typeof value === "string") return value.trim() === "";
  if (typeof value === "boolean") return false;
  if (typeof value === "number") return Number.isNaN(value);
  if (value instanceof Date) return Number.isNaN(value.getTime());
  if (Array.isArray(value)) return value.every((item) => isEmptyValue(item));
  if (typeof value === "object")
    return isEmptyValue((value as { id?: unknown }).id);
  return true;
};

/**
 * The rules the record's profile states, answered against the current form
 * values. A rule is only evaluated for a field the form actually carries:
 * a field the editor never rendered has no verdict here, and the server
 * keeps it.
 */
export const clientFindings = (
  rules: ProfileRule[] | undefined,
  values: Record<string, unknown>,
): Finding[] => {
  if (!Array.isArray(rules)) return [];
  const findings: Finding[] = [];
  for (const rule of rules) {
    if (
      typeof rule?.id !== "string" ||
      typeof rule?.message !== "string" ||
      typeof rule?.field !== "string" ||
      !rule.field
    ) {
      // a rule without an assessable id, message or field is the server's to
      // judge: it points at /data, which no form value decides
      continue;
    }
    const field = snakeToCamel(rule.field);
    const carries = field in values || rule.field in values;
    if (!carries) continue;
    const value = field in values ? values[field] : values[rule.field];
    if (!isEmptyValue(value)) continue;
    findings.push({
      key: `client:${rule.id}`,
      ruleId: rule.id,
      field,
      severity: rule.severity === "warning" ? "warning" : "error",
      detail: rule.message,
      family: rule.family,
      origin: "client",
    });
  }
  return findings;
};

interface JsonApiErrorLike {
  source?: { pointer?: string };
  detail?: string;
  rule?: string;
  severity?: string;
  meta?: { family?: string };
}

/** the json:api pointers #1243 answers findings through */
const POINTER_PREFIXES = ["/data/attributes/", "/data/relationships/"];

/**
 * The json:api error objects of a refused save, read into findings. The
 * data provider hands the raw members through on the HttpError body:
 * `source.pointer` names the field to jump to, `rule` cites the rule id
 * (#1243's `findings_to_errors`), and an error naming no pointer is a global
 * finding the rail shows unanchored.
 */
export const serverFindings = (errors: unknown[]): Finding[] =>
  errors
    .filter(
      (error): error is JsonApiErrorLike =>
        typeof error === "object" && error !== null,
    )
    .map((error, index) => {
      const pointer = error.source?.pointer ?? "";
      const prefixed = POINTER_PREFIXES.find((prefix) =>
        pointer.startsWith(prefix),
      );
      const field = prefixed ? pointer.slice(prefixed.length) : undefined;
      return {
        key: `server:${index}:${error.rule ?? pointer}`,
        ruleId: typeof error.rule === "string" ? error.rule : undefined,
        field: field || undefined,
        severity: error.severity === "warning" ? "warning" : "error",
        detail: error.detail ?? "",
        family: error.meta?.family,
        origin: "server" as const,
      };
    });

/**
 * The findings the rail shows: the server verdict first — it evaluated the
 * resulting document — and the client pre-validation for the rule ids the
 * server did not answer (never yet, or an error the write did not reach).
 */
export const mergeFindings = (
  client: Finding[],
  server: Finding[],
): Finding[] => {
  const answered = new Set(
    server.map((finding) => finding.ruleId).filter(Boolean),
  );
  return [
    ...server,
    ...client.filter(
      (finding) => !finding.ruleId || !answered.has(finding.ruleId),
    ),
  ];
};

/** how many of the profile's mandatory fields the current values fill */
export const completeness = (
  mandatory: string[],
  values: Record<string, unknown>,
): { filled: number; total: number } => ({
  filled: mandatory.filter((source) => !isEmptyValue(values[source])).length,
  total: mandatory.length,
});
