/// <reference types="vite/client" />

// The build-time injections of vite.config.mjs (#1579): the canonical
// application version from the root VERSION file, and the exact revision the
// builder stamped ("dev" when nobody stamped one). Both are `define`d, so
// they are string literals in the bundle, never runtime lookups.
interface ImportMetaEnv {
    readonly VITE_APP_VERSION: string;
    readonly VITE_BUILD_REVISION: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}
