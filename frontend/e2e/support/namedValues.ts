import { DATASET_TITLE_ABSENT, DATASET_TITLE_EMPTY, DATASET_TITLE_VALID, SEARCH_TERM, WMS_TITLE } from "../helpers/fixtures";

// Named values of the step grammar (#1688, "Directory layout"): a feature file
// names a value, never a uuid or a string a fixture happens to carry. The seeded
// values come from helpers/fixtures.ts — the same source the plain spec suite
// reads — so the Gherkin layer and the spec layer can never disagree about what
// the acceptance stack is seeded with.

export const NAMED_VALUES: Record<string, string> = {
  "{seed.dataset.title}": DATASET_TITLE_VALID,
  "{seed.dataset.title.empty}": DATASET_TITLE_EMPTY,
  "{seed.dataset.title.absent}": DATASET_TITLE_ABSENT,
  "{seed.dataset.searchterm}": SEARCH_TERM,
  "{seed.wms.title}": WMS_TITLE,
};

export const NAMED_VALUE_NAMES = Object.keys(NAMED_VALUES);

/** Resolve `{seed.*}` placeholders inside a step argument; an unknown name fails loudly. */
export const resolveNamedValue = (value: string): string => {
  const direct = NAMED_VALUES[value];
  if (direct !== undefined) return direct;
  return value.replace(/\{seed\.[a-z.]+\}/gi, (placeholder) => {
    const named = NAMED_VALUES[placeholder.toLowerCase()];
    if (named === undefined) throw new Error(`unknown named value "${placeholder}" — known: ${NAMED_VALUE_NAMES.join(", ")}`);
    return named;
  });
};
