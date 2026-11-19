// The About display of the footer (#1579): the frontend's own version is
// always named; a backend that answers a different version is shown as a
// warning naming both sides; an unstamped build is marked as a development
// revision. The translation runs through the real i18nProvider so the keys
// and their %{interpolation} are pinned against the real catalogs.

import { AdminContext, testDataProvider } from 'react-admin';

import { cleanup, render, screen } from '@testing-library/react';
import polyglotI18nProvider from 'ra-i18n-polyglot';
import { afterEach, describe, expect, it } from 'vitest';

import de from '../../i18n/de';
import en from '../../i18n/en';
import { APP_VERSION } from './appVersion';
import AppVersionInfo from './AppVersionInfo';

afterEach(cleanup);

// the real English catalog through the same provider shape the app uses, so
// the keys and their %{interpolation} are pinned against the real messages
const renderInfo = (backendVersion?: string | null) => render(
    <AdminContext
      dataProvider={testDataProvider()}
      i18nProvider={polyglotI18nProvider(() => en, 'en')}
    >
        <AppVersionInfo backendVersion={backendVersion} />
    </AdminContext>,
);

describe('AppVersionInfo (#1579)', () => {
    it('names the canonical version and marks the development revision', () => {
        renderInfo(undefined);
        // vitest runs as an unstamped build: the dev marker must show
        expect(screen.getByText(new RegExp(`v${APP_VERSION.replace('+', '\\+')}`)))
            .toBeInTheDocument();
        expect(screen.getByText('development revision', { exact: false }))
            .toBeInTheDocument();
        expect(screen.queryByTestId('WarningAmberOutlinedIcon')).not
            .toBeInTheDocument();
    });

    it('stays quiet while the backend has not answered a version', () => {
        renderInfo(null);
        expect(screen.queryByTestId('WarningAmberOutlinedIcon')).not
            .toBeInTheDocument();
    });

    it('is satisfied when the backend answers the same version', () => {
        renderInfo(APP_VERSION);
        expect(screen.queryByTestId('WarningAmberOutlinedIcon')).not
            .toBeInTheDocument();
        expect(screen.getByLabelText(`MrMap application version v${APP_VERSION}`))
            .toBeInTheDocument();
    });

    it('warns and names both sides when the backend answers another version', () => {
        renderInfo('9.9.9');
        expect(screen.getByTestId('WarningAmberOutlinedIcon')).toBeInTheDocument();
        expect(screen.getByLabelText(
            `The frontend is v${APP_VERSION} but the backend answers v9.9.9 `
            + '- this deployment mixes two builds',
        )).toBeInTheDocument();
    });

    it('carries the footer keys in both catalogs', () => {
        // the project rule: every key in en AND de, with the same tokens
        for (const catalog of [en, de] as const) {
            const footer = (catalog as { footer?: Record<string, string> }).footer;
            expect(footer, 'footer section').toBeDefined();
            for (const key of ['appVersion', 'versionMismatch', 'devRevision']) {
                expect(typeof footer?.[key]).toBe('string');
            }
            expect(footer?.appVersion).toContain('%{version}');
            expect(footer?.versionMismatch).toContain('%{frontend}');
            expect(footer?.versionMismatch).toContain('%{backend}');
        }
    });
});
