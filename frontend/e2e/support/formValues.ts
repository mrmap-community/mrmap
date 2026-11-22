// Values a scenario needs but cannot carry in a feature file (#1688): a name no
// other machine's row can have, a timestamp. A feature file never carries one
// inline — it names it and this module resolves the name, so two nightly runs
// against one database cannot collide and then claim they failed for
// different reasons.

let counter = 0;

const RESOLVERS: Record<string, () => string> = {
  uniqueName: () => {
    counter += 1;
    const label = process.env.E2E_RUN_LABEL ?? `pid-${process.pid}`;
    return `e2e-${label}-${counter}-${Math.random().toString(36).slice(2, 7)}`;
  },
  now: () => new Date().toISOString(),
};

export const GENERATED_NAMES = Object.keys(RESOLVERS);

export const isGeneratedName = (value: string) => /^\{\{\s*[A-Za-z][A-Za-z0-9]*\s*\}\}$/.test(value.trim());

export const resolveFormValue = (raw: string) => {
  const name = raw.trim().match(/^\{\{\s*([A-Za-z][A-Za-z0-9]*)\s*\}\}$/)?.[1];
  if (!name) return raw;
  const resolver = RESOLVERS[name];
  if (!resolver) throw new Error(`unknown generated value "{{ ${name} }}" — known: ${GENERATED_NAMES.join(", ")}`);
  return resolver();
};
