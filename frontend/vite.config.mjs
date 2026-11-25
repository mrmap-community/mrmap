import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { defaultExclude } from 'vitest/config';

// The canonical application version is the file `VERSION` at the
// repository root (#1579); this file is the frontend's build-time read of it.
// The path resolves relative to this config, which is the repository root on
// a checkout, `/VERSION` in the nginx compile image (`COPY ./VERSION
// /VERSION` in docker/nginx/nginx.Dockerfile, the parent of its /app), and
// `/opt/mrmap/VERSION` in the frontend-tests container (the bind added to the
// service in docker-compose.dev.yml, the parent of /opt/mrmap/frontend). A
// missing or invalid file fails every entry point that loads this config -
// build, dev server and vitest - on purpose: there is no fallback version.
// The grammar is SemVer 2.0.0 exactly (prerelease and +build metadata are
// expressible); scripts/canonical_version.py validates with the same rules.
export const SEMVER_STRICT =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$/;

// A normal config load sees this module through a `file:` URL; a spec that
// imports this file runs under vitest's module server, where import.meta.url
// is an http URL under `/@fs/` and its pathname is the real absolute path.
// Both spellings are mapped to one readable path.
const canonicalVersionPath = (url) => url.protocol === 'file:'
    ? fileURLToPath(url)
    : decodeURIComponent(url.pathname).replace(/^\/@fs/, '');

export const CANONICAL_VERSION_FILE =
    canonicalVersionPath(new URL('../VERSION', import.meta.url));

const readCanonicalVersion = () => {
    let raw;
    try {
        raw = readFileSync(CANONICAL_VERSION_FILE, 'utf8');
    } catch {
        throw new Error(
            `the canonical version file is missing: expected one strict SemVer line at ${CANONICAL_VERSION_FILE}`);
    }
    const version = raw.trim();
    if (!SEMVER_STRICT.test(version)) {
        throw new Error(
            `the canonical version file holds an invalid version: ${CANONICAL_VERSION_FILE} reads ${JSON.stringify(raw)}`);
    }
    return version;
};

// The exact revision of this build, injected by the builder through
// MRMAP_BUILD_REVISION (docker-compose.yml passes the deployer's .env value
// into docker/nginx/nginx.Dockerfile). "dev" marks a build nobody stamped -
// a checkout, a dev server, a spec run - so the UI can tell an exact build
// apart from an unstamped one; the About display distinguishes both.
const buildRevision = () => (process.env.MRMAP_BUILD_REVISION ?? '').trim() || 'dev';

export const MRMAP_APP_VERSION = readCanonicalVersion();

// The optional test-only Compose layer supplies the same limit to Django
// and Vitest. Unset keeps Vitest's normal throughput defaults. Keep the pool,
// isolation, test selection and coverage configuration shared by both modes.
export const testWorkerOptions = (raw) => {
    if (raw === undefined) return {};
    if (!/^[1-9]\d*$/.test(raw) || !Number.isSafeInteger(Number(raw))) {
        throw new Error('MRMAP_TEST_WORKERS must be a positive integer');
    }
    return { maxWorkers: Number(raw) };
};

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    test: {
        ...testWorkerOptions(process.env.MRMAP_TEST_WORKERS),
        globals: true,
        environment: 'jsdom',
        setupFiles: './tests/setup.js',
        // Keep the Playwright browser-acceptance harness out of this run
        // (#1034): frontend/e2e is not a vitest suite. It carries its own
        // pinned package.json and runs in the mcr.microsoft.com/playwright
        // image (frontend/e2e/README.md); the application's node_modules has
        // no @playwright/test, so its *.spec.ts files would only ever fail
        // here on the import. The vitest defaults stay - they exclude the
        // tooling configs and node_modules around this project.
        exclude: [...defaultExclude, 'e2e/**'],
        coverage: {
            provider: 'istanbul',
            include: ['src/**/*.{js,jsx,ts,tsx}'],
            exclude: ['src/**/*.spec.*', 'src/**/tests/**', 'src/**/*.d.ts'],
            reporter: ['text', 'html', 'lcov', 'json-summary'],
            reportOnFailure: true,
            thresholds: { lines: 52, statements: 51, branches: 49, functions: 48 }
        }
    },
    define: {
        'process.env': process.env,
        // baked into the bundle at build time, read through import.meta.env
        'import.meta.env.VITE_APP_VERSION': JSON.stringify(MRMAP_APP_VERSION),
        'import.meta.env.VITE_BUILD_REVISION': JSON.stringify(buildRevision()),
    },
    server: {
        host: true,
    },
    // Root-absolute on purpose. The app is always served from the root of the
    // origin (docker/nginx/mrmap.conf serves dist/ under `location /`), and the
    // built index.html is returned for every route by the SPA fallback. A
    // relative base ('./') makes the browser resolve ./assets/* against the
    // *route path*, so any deep link with 2+ path segments requests the bundle
    // under the route, gets index.html (200, text/html) from the fallback and
    // never boots - stuck at "Loading..." (#941). The dev server serves the
    // same routes from '/' as well, so '/' is correct for both.
    base: '/',
    optimizeDeps: {
        include: ['@mui/material/Tooltip', '@emotion/styled'],
    }
    // resolve: {
    //     alias: {
    //         '@api-platform/admin/src/InputGuesser': './node_modules/@api-platform/admin/src/InputGuesser'
    //     }
    // }

});
