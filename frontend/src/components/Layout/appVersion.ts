// The frontend's own view of the canonical application version (#1579).
// Both injected values come from vite.config.mjs at build time: the version
// is the root `VERSION` file baked into the bundle, the revision is the exact
// build the builder stamped into MRMAP_BUILD_REVISION ("dev" when nobody
// stamped one - a checkout, a dev server, a spec run). The rules of "which
// side is which" live in this module so the About display and any later
// reader agree on them. The helpers take their inputs explicitly (the
// injected constants are the defaults) so the rules stay testable at both
// ends of a mismatch, not only at the one the current build happens to have.

export const APP_VERSION: string = import.meta.env.VITE_APP_VERSION;

export const BUILD_REVISION: string = import.meta.env.VITE_BUILD_REVISION ?? 'dev';

// true when the bundle carries no stamped revision
export const isDevelopmentRevision = (revision: string = BUILD_REVISION): boolean =>
    revision === 'dev';

// The frontend and the backend answer the same string when both were built
// from one checkout: the canonical VERSION file is the source of both, so any
// difference is a real deployment skew, worth showing, not normalization
// noise. An unknown (not yet loaded) backend version is no answer at all.
export const backendVersionMismatch = (
    backendVersion?: string | null,
    appVersion: string = APP_VERSION,
): boolean =>
    typeof backendVersion === 'string' && backendVersion.trim() !== ''
    && backendVersion.trim() !== appVersion;

// The version the About display shows: the canonical version, carrying the
// stamped revision as build metadata when the builder provided one and the
// version itself does not already name a revision.
export const displayVersion = (
    appVersion: string = APP_VERSION,
    revision: string = BUILD_REVISION,
): string =>
    !isDevelopmentRevision(revision) && !appVersion.includes('+')
        ? `${appVersion}+${revision}`
        : appVersion;
