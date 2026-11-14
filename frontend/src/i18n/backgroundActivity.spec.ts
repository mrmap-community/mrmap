import lodashGet from "lodash/get";
import { describe, expect, it } from "vitest";

import de from "./de";
import en from "./en";

/**
 * The background job surfaces - the AppBar activity panel and the background
 * process screens - draw every label from the blocks below (#1209, epic
 * #1203): a key which exists only in one language makes the panel answer the
 * raw key or the other language's string right where the user needs to read
 * what failed. The parity assertion is the cheap guard for that; the
 * harvesting screens have the same guard in harvesting.spec.ts.
 */
const backgroundBlocks = ["backgroundActivity"];

const leafPaths = (value: unknown, prefix = ""): string[] =>
  value !== null && typeof value === "object"
    ? Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
        leafPaths(child, prefix === "" ? key : `${prefix}.${key}`),
      )
    : [prefix];

describe("background notification translations", () => {
  it.each(backgroundBlocks)(
    "%s carries the same keys in English and German",
    block => {
      const english = lodashGet(en, block);
      const german = lodashGet(de, block);

      expect(english, `${block} is missing in en`).toBeDefined();
      expect(german, `${block} is missing in de`).toBeDefined();
      expect(leafPaths(german).sort()).toEqual(leafPaths(english).sort());
    },
  );

  it.each(backgroundBlocks)(
    "%s answers non-empty strings in both languages",
    block => {
      for (const messages of [en, de]) {
        for (const path of leafPaths(lodashGet(messages, block))) {
          const value = lodashGet(lodashGet(messages, block), path);
          expect(typeof value, `${block}.${path}`).toBe("string");
          expect((value as string).trim(), `${block}.${path}`).not.toBe("");
        }
      }
    },
  );

  it("names every status a background process can reach", () => {
    // the status chip of the panel falls back to the raw status word when a
    // status is untranslated - a silent regression in the one label that
    // carries the failure (notify.ProcessStatusEnum has five members)
    const statuses = ["pending", "running", "completed", "failed", "aborted"];
    for (const messages of [en, de]) {
      for (const status of statuses) {
        const value = lodashGet(
          messages,
          `backgroundActivity.status.${status}`,
        );
        expect(typeof value, status).toBe("string");
        expect((value as string).trim(), status).not.toBe("");
      }
    }
  });

  it("names every phase the registration reports", () => {
    // a registration writes its phases as keys, never as sentences
    // (`registry/views/service.py`, `registry/tasks/service.py`), and the
    // task base of notify ends the process with `completed`; a key missing
    // here answers the raw key right where the operator reads the progress,
    // which is the regression #1267 closes out
    const phases = [
      "background_process_created",
      "download_capabilities",
      "parse_capabilities",
      "persist_service",
      "collect_metadata_records",
      "completed",
    ];
    for (const messages of [en, de]) {
      for (const phase of phases) {
        const value = lodashGet(messages, `backgroundActivity.phases.${phase}`);
        expect(typeof value, phase).toBe("string");
        expect((value as string).trim(), phase).not.toBe("");
      }
    }
  });

  it("names every error kind a failed reference reports", () => {
    // the collection of #1263 stores the reason of a lost reference as one
    // of the six words of `registry/enums/harvesting.py:ReferenceErrorKind`;
    // the references table of #1265 looks the word up here and a missing key
    // answers the raw kind right where the editor decides the retry
    const kinds = [
      "fetch_timeout",
      "fetch_unreachable",
      "no_content",
      "no_identifiable_record",
      "unsupported_kind",
      "import_failed",
    ];
    for (const messages of [en, de]) {
      for (const kind of kinds) {
        const value = lodashGet(
          messages,
          `backgroundActivity.references.errorKinds.${kind}`,
        );
        expect(typeof value, kind).toBe("string");
        expect((value as string).trim(), kind).not.toBe("");
      }
    }
  });
});
