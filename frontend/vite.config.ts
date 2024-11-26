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
            provider: 'istanbul'
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
