import fs from "node:fs";
import path from "node:path";

// Artifact redaction of the systemtest contract (#1688, "Artifact redaction"):
// nothing that leaves the runner may name a session credential. One module so
// the PR smoke, the nightly tier and the exploratory workflow (#1698, #1699)
// share the same implementation instead of each writing its own scrubber.

export const REDACTED = "[redacted]";

export const SENSITIVE_COOKIE_NAMES = ["sessionid", "csrftoken"];
export const SENSITIVE_HEADER_NAMES = [
  "authorization",
  "cookie",
  "set-cookie",
  "x-csrftoken",
  "x-session-api-key",
];

const SENSITIVE_NAMES = new Set([...SENSITIVE_COOKIE_NAMES, ...SENSITIVE_HEADER_NAMES].map((name) => name.toLowerCase()));

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

const redactTree = (value: Json): Json => {
  if (Array.isArray(value)) return value.map(redactTree);
  if (value === null || typeof value !== "object") return value;
  const target: Record<string, unknown> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (SENSITIVE_NAMES.has(key.toLowerCase())) {
      target[key] = typeof entry === "string" && entry !== "" ? REDACTED : redactTree(entry as Json);
      continue;
    }
    target[key] = redactTree(entry as Json);
  }
  return target;
};

const walk = (dir: string, files: string[] = []): string[] => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, files);
    else files.push(full);
  }
  return files;
};

const isStorageState = (name: string) => name.includes("storage-state") || name === "state.json";

// A storage state is a login: its cookie and localStorage values are never
// shipped, only their names. Trace files are zip archives and belong to the
// tracer; the plain JSON artifacts of the run are handled here.
export const redactArtifacts = (dir: string) => {
  const summary = { redacted: [] as string[], storageStates: 0, scanned: 0 };
  if (!fs.existsSync(dir)) return summary;
  for (const file of walk(dir)) {
    const name = path.basename(file);
    if (!name.endsWith(".json")) continue;
    summary.scanned += 1;
    const text = fs.readFileSync(file, "utf8");
    let parsed: Json;
    try {
      parsed = JSON.parse(text) as Json;
    } catch {
      continue;
    }
    const redacted = redactTree(parsed);
    if (isStorageState(name)) {
      summary.storageStates += 1;
      const state = redacted as { cookies?: { value?: unknown }[]; origins?: { localStorage?: { value?: unknown }[] } };
      for (const cookie of state.cookies ?? []) if (cookie.value) cookie.value = REDACTED;
      for (const origin of state.origins ?? []) {
        for (const entry of origin.localStorage ?? []) if (entry.value) entry.value = REDACTED;
      }
    }
    const next = JSON.stringify(redacted, null, 2);
    if (next !== text) {
      fs.writeFileSync(file, next);
      summary.redacted.push(path.relative(dir, file));
    }
  }
  return summary;
};

// A credential worth failing the run over: a session-ish name with a value long
// enough not to be a label, or a session key-shaped hex string.
const SECRET_IN_TEXT =
  /"(?:sessionid|csrftoken|authorization|cookie)"\s*:\s*"(?!\[redacted\])[A-Za-z0-9!#$%&'*+.^_`|~=-]{12,}"/i;

export const leakedCredentialFiles = (dir: string) => {
  if (!fs.existsSync(dir)) return [];
  return walk(dir)
    .filter((file) => file.endsWith(".json"))
    .filter((file) => SECRET_IN_TEXT.test(fs.readFileSync(file, "utf8")))
    .map((file) => path.relative(dir, file));
};
