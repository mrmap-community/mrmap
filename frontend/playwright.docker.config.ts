// playwright.docker.config.ts
import type { PlaywrightTestConfig } from '@playwright/test';
import localConfig from './playwright.config';

const config: PlaywrightTestConfig = localConfig;

if (localConfig.use) {
  localConfig.use.baseURL = 'https://mrmap-nginx';
} else {
  localConfig.use = {
    baseURL: 'https://mrmap-nginx',
    trace: 'on-first-retry',
    ignoreHTTPSErrors: true,
    screenshot: 'only-on-failure',
  };
}

export default config;
