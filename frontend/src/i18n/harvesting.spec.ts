import lodashGet from "lodash/get";
import { describe, expect, it } from "vitest";

import de from "./de";
import en from "./en";

/**
 * The harvesting screens draw every label from the `resources` blocks and the
 * harvesting blocks of the translations (#1085): a key that exists only in one
 * language makes the screen answer the key or the other language's string.
 */
const harvestingBlocks = [
  "resources.HarvestingJob",
  "resources.PeriodicHarvestingJob",
  "resources.HarvestingLog",
  "resources.TemporaryMdMetadataFile",
  "resources.CatalogueServiceUpdateJob",
  "resources.HarvestedMetadataRelation",
  // `resources.BackgroundProcess` was read only by the snackbar alert, which
  // the Job Center (#1203) replaced together with the block.
  "harvestingStats",
  "cronInput",
  // the collection card of a service is the second user of this word family:
  // one vocabulary for both paths which collect (#1266, D6 of #1256)
  "collectionActivity",
];

const leafPaths = (value: unknown, prefix = ""): string[] =>
  value !== null && typeof value === "object"
    ? Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
        leafPaths(child, prefix === "" ? key : `${prefix}.${key}`),
      )
    : [prefix];

// React-Admin's `ra` catalog is supplied by the English package and a separate
// German catalog. Check the MrMap application messages, not those framework
// defaults (which include an intentionally blank boolean option).
const applicationMessages = {
  en: Object.fromEntries(Object.entries(en).filter(([key]) => key !== "ra")),
  de: Object.fromEntries(Object.entries(de).filter(([key]) => key !== "ra")),
};

const placeholders = (message: string): string[] =>
  [...new Set(Array.from(message.matchAll(/%\{([^{}]+)\}/g), ([, name]) => name.trim()))].sort();

describe("application translations", () => {
  it("carries the same application keys in English and German", () => {
    expect(leafPaths(applicationMessages.de).sort()).toEqual(
      leafPaths(applicationMessages.en).sort(),
    );
  });

  it.each(Object.entries(applicationMessages))(
    "%s answers non-empty strings for every application key",
    (locale, messages) => {
      for (const path of leafPaths(messages)) {
        const value = lodashGet(messages, path);
        expect(typeof value, `${locale}.${path}`).toBe("string");
        expect((value as string).trim(), `${locale}.${path}`).not.toBe("");
      }
    },
  );

  it("keeps interpolation placeholders consistent between languages", () => {
    for (const path of leafPaths(applicationMessages.en)) {
      const english = lodashGet(applicationMessages.en, path);
      const german = lodashGet(applicationMessages.de, path);
      expect(typeof english, `en.${path}`).toBe("string");
      expect(typeof german, `de.${path}`).toBe("string");
      expect(placeholders(german as string), path).toEqual(
        placeholders(english as string),
      );
    }
  });
});

describe("harvesting translations", () => {
  it.each(harvestingBlocks)(
    "%s carries the same keys in English and German",
    block => {
      const english = lodashGet(en, block);
      const german = lodashGet(de, block);

      expect(english, `${block} is missing in en`).toBeDefined();
      expect(german, `${block} is missing in de`).toBeDefined();
      expect(leafPaths(german).sort()).toEqual(leafPaths(english).sort());
    },
  );

  it.each(harvestingBlocks)("%s answers non-empty strings in both languages", block => {
    for (const messages of [en, de]) {
      for (const path of leafPaths(lodashGet(messages, block))) {
        const value = lodashGet(lodashGet(messages, block), path);
        expect(typeof value, `${block}.${path}`).toBe("string");
        expect((value as string).trim(), `${block}.${path}`).not.toBe("");
      }
    }
  });

  it("has no typo left over in a translation key value", () => {
    for (const messages of [en, de]) {
      for (const block of harvestingBlocks) {
        for (const path of leafPaths(lodashGet(messages, block))) {
          const value = String(lodashGet(lodashGet(messages, block), path));
          expect(value).not.toMatch(/wating|serach/);
        }
      }
    }
  });
});
