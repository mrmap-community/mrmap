// The About display's version rules (#1579): the injected constants must
// equal what the build configured, and the mismatch/dev rules hold for every
// pair of answers, not only the one this build happens to carry. The chain
// "VERSION file -> vite.config define -> import.meta.env constant" is pinned
// here from its runtime end; vite.config.spec.mjs pins its file end, so the
// two together leave no link unchecked.

import { describe, expect, it } from 'vitest';

import config from '../../../vite.config.mjs';
import {
    APP_VERSION,
    BUILD_REVISION,
    backendVersionMismatch,
    displayVersion,
    isDevelopmentRevision,
} from './appVersion';

// what the vite `define` baked for this run (JSON string literals)
const defined = (key: string): string => {
    const define = (config as { define?: Record<string, string | undefined> }).define;
    const raw = define?.[key];
    if (typeof raw !== 'string') {
        throw new Error(`the vite config defines no ${key}`);
    }
    return JSON.parse(raw) as string;
};

describe('the injected version (#1579)', () => {
    it('equals what the build config defined for it', () => {
        expect(APP_VERSION).toBe(defined('import.meta.env.VITE_APP_VERSION'));
    });

    it('carries the build revision the config defined', () => {
        expect(BUILD_REVISION).toBe(defined('import.meta.env.VITE_BUILD_REVISION'));
    });

    it('marks an unstamped build as the development revision', () => {
        // vitest is not a builder: no MRMAP_BUILD_REVISION was set here
        expect(BUILD_REVISION).toBe('dev');
        expect(isDevelopmentRevision()).toBe(true);
        expect(isDevelopmentRevision('9f8e7d6')).toBe(false);
    });
});

describe('the frontend/backend mismatch rule', () => {
    it('has no opinion while the backend has not answered', () => {
        expect(backendVersionMismatch(undefined, '0.1.0')).toBe(false);
        expect(backendVersionMismatch(null, '0.1.0')).toBe(false);
        expect(backendVersionMismatch('   ', '0.1.0')).toBe(false);
    });

    it('is silent when both sides carry the canonical version', () => {
        expect(backendVersionMismatch('0.1.0', '0.1.0')).toBe(false);
        expect(backendVersionMismatch(' 0.1.0\n', '0.1.0')).toBe(false);
    });

    it('names a real deployment skew, prereleases included', () => {
        expect(backendVersionMismatch('0.2.0', '0.1.0')).toBe(true);
        expect(backendVersionMismatch('0.1.0-rc.1', '0.1.0')).toBe(true);
        expect(backendVersionMismatch('0.1.0+9f8e7d6', '0.1.0')).toBe(true);
    });
});

describe('the display version', () => {
    it('stays bare for a development build', () => {
        expect(displayVersion('0.1.0', 'dev')).toBe('0.1.0');
    });

    it('carries the stamped revision as build metadata', () => {
        expect(displayVersion('0.1.0', '9f8e7d6')).toBe('0.1.0+9f8e7d6');
    });

    it('does not stack a revision onto a version that already names one', () => {
        expect(displayVersion('0.2.0-rc.1+9f8e7d6', '1234abc')).toBe('0.2.0-rc.1+9f8e7d6');
    });
});
