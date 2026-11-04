import { describe, expect, it } from "vitest";

import config from "./vite.config.mjs";

// Regression guard for #941: deep links with 2+ path segments must boot the
// app. The built index.html is served by the SPA fallback for every route, so
// its asset URLs must resolve to the origin root no matter how deep the URL
// path is. With the old relative base "./" a hard navigation to
// /DatasetMetadataRecord/<uuid>/show made the browser fetch
// /DatasetMetadataRecord/<uuid>/assets/index-*.js, the nginx fallback answered
// with index.html (200 text/html) and the app never started.

describe("the vite build base (#941)", () => {

  it("is root-absolute, not relative", () => {
    expect(typeof config.base).toBe("string");
    expect(config.base).toMatch(/^\//);
    expect(config.base.startsWith("./")).toBe(false);
  });

  it("keeps root-absolute asset URLs at the origin root on a deep route", () => {
    const deep = "http://localhost/DatasetMetadataRecord/d9a54f4f-0000-0000-0000-000000000000/show";
    expect(new URL("/assets/index-abc123.js", deep).pathname).toBe("/assets/index-abc123.js");
  });

  it("documents why a relative base breaks exactly those routes", () => {
    // The trap this config must never fall back into: a relative reference
    // resolves against the directory of the current path, so it drifts by the
    // depth of the route - the failure that left users stuck at "Loading...".
    const deep = "http://localhost/DatasetMetadataRecord/d9a54f4f-0000-0000-0000-000000000000/show";
    expect(new URL("./assets/index-abc123.js", deep).pathname)
      .toBe("/DatasetMetadataRecord/d9a54f4f-0000-0000-0000-000000000000/assets/index-abc123.js");
    const one = "http://localhost/Language";
    expect(new URL("./assets/index-abc123.js", one).pathname).toBe("/assets/index-abc123.js");
  });

});
