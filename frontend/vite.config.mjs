import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [react()],
    test: {
        globals: true,
        environment: 'jsdom',
        setupFiles: './tests/setup.js',
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
        include: ['@mui/material/Tooltip', '@mui/x-data-grid', '@emotion/styled'],
    }
    // resolve: {
    //     alias: {
    //         '@api-platform/admin/src/InputGuesser': './node_modules/@api-platform/admin/src/InputGuesser'
    //     }
    // }

});
