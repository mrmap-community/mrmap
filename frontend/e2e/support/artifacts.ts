import fs from "node:fs";
import path from "node:path";

import { leakedCredentialFiles, redactArtifacts } from "./redaction";

// Where the artifacts of a run land and the two decisions taken on them
// (#1688, "Artifact redaction").
//
// `outputDir` is `.output` (playwright.config.ts), so the artifacts of a
// failing scenario live under `.output/<file>-<title>/` and the login state of
// the setup project is `.output/state.json`. The pass has to cover the whole
// root: the first version pointed at `.output/bdd`, a directory no run ever
// creates, so `redactArtifacts` returned at its `existsSync` guard and reported
// a clean run while scrubbing nothing (#1689 review, finding 3).

export const OUTPUT_DIR = process.env.E2E_OUTPUT_DIR ?? ".output";

const isStorageStateFile = (name: string) => name === "state.json" || name.includes("storage-state");

const walk = (dir: string, files: string[] = []): string[] => {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, files);
    else files.push(full);
  }
  return files;
};

/**
 * Scrub the JSON artifacts of a run and remove the login state.
 *
 * The login state is the input of the `chromium` and `bdd` projects, which
 * Playwright reads when the run starts, so it can only go after the run —
 * which is why this runs from the reporter and not from a worker `AfterAll`.
 * #1688: "never ship a storage state together with an artifact"; the setup
 * project rebuilds it on the next run, so removing it costs a login, not a run.
 *
 * `leaked` names what still carries a credential: a credential-shaped value the
 * scrubber could not remove, or a storage state that could not be deleted.
 */
export const protectArtifacts = (dir = OUTPUT_DIR) => {
  const exists = fs.existsSync(dir);
  const summary = exists ? redactArtifacts(dir) : { redacted: [] as string[], storageStates: 0, scanned: 0 };
  const states = exists ? walk(dir).filter((file) => isStorageStateFile(path.basename(file))) : [];
  for (const state of states) fs.rmSync(state, { force: true });
  const undeleted = states.filter((state) => fs.existsSync(state));
  return {
    dir,
    scanned: summary.scanned,
    redacted: summary.redacted,
    storageStates: summary.storageStates + states.length,
    leaked: [...new Set([...leakedCredentialFiles(dir), ...undeleted])].map((file) => path.relative(dir, file)),
  };
};
