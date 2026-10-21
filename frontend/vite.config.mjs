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
    base: './',
    optimizeDeps: {
        include: ['@mui/material/Tooltip', '@mui/x-data-grid', '@emotion/styled'],
    }
    // resolve: {
    //     alias: {
    //         '@api-platform/admin/src/InputGuesser': './node_modules/@api-platform/admin/src/InputGuesser'
    //     }
    // }

});
