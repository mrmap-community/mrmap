import type { Reporter } from "@playwright/test/reporter";

import { OUTPUT_DIR, protectArtifacts } from "./artifacts";

// The closing check of the acceptance line (#1688, "Artifact redaction").
//
// A worker-scoped `AfterAll` cannot carry this: it fires after the last
// scenario of the *worker*, before the reporters write `.output/results.json`,
// and an error there is not necessarily red. A reporter's `onEnd` runs once,
// after the whole run and after the artifacts exist — and Playwright turns a
// throw in it into a failed run (`hasReporterErrors()` flips the status from
// passed to failed), which is what makes "no credential leaves the runner" an
// assertion instead of a comment.

class ArtifactGuard implements Reporter {
  onEnd() {
    const { scanned, redacted, storageStates, leaked, dir } = protectArtifacts(OUTPUT_DIR);
    console.log(
      `[e2e] artifacts: ${scanned} json file(s) scanned, ${redacted.length} redacted, ` +
      `${storageStates} storage state(s) removed from ${dir}`,
    );
    if (leaked.length > 0) {
      throw new Error(
        `[e2e] credential(s) would leave the runner in ${dir}: ${leaked.join(", ")} — ` +
        "see support/redaction.ts and #1688 'Artifact redaction'",
      );
    }
  }
}

export default ArtifactGuard;
