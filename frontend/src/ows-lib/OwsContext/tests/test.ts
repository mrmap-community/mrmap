import { test } from 'vitest';

import { OWSContext } from '../core';
import { reducedKarteRpFeatures, karteRpFeatures } from './data';

export interface OwsContextFixture {
  karteRp: OWSContext;
  reducedKarteRp: OWSContext;
}

export const owsContextTest = test.extend<OwsContextFixture>({
  karteRp: async ({ task: _task }, use) => {
    const context = new OWSContext(undefined, karteRpFeatures);
    context.sortFeaturesByFolder();
    await use(context);
  },
  reducedKarteRp: async ({ task: _task }, use) => {
    const context = new OWSContext(undefined, reducedKarteRpFeatures);
    context.sortFeaturesByFolder();
    await use(context);
  },
});
