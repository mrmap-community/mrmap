import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import config, { CANONICAL_VERSION_FILE, MRMAP_APP_VERSION, SEMVER_STRICT, testWorkerOptions } from "./vite.config.mjs";

describe("test concurrency (#1619)", () => {
  it("keeps normal Vitest defaults when no limit is supplied", () => {
    expect(testWorkerOptions(undefined)).toEqual({});
  });

  it("limits workers without changing isolation or coverage", () => {
    expect(testWorkerOptions("1")).toEqual({ maxWorkers: 1 });
    expect(testWorkerOptions("2")).toEqual({ maxWorkers: 2 });
    expect(testWorkerOptions("4")).toEqual({ maxWorkers: 4 });
  });

  it("refuses invalid limits instead of silently selecting another mode", () => {
    for (const raw of ["", "0", "-1", "1.5", "auto", "9007199254740992"]) {
      expect(() => testWorkerOptions(raw)).toThrow("MRMAP_TEST_WORKERS");
    }
  });
});

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

describe("the canonical version injection (#1579)", () => {

  it("bakes the canonical VERSION file into the bundle", () => {
    const canonical = readFileSync(CANONICAL_VERSION_FILE, "utf8").trim();
    expect(MRMAP_APP_VERSION).toBe(canonical);
    expect(config.define["import.meta.env.VITE_APP_VERSION"])
      .toBe(JSON.stringify(canonical));
  });

  it("defines the build revision as a string literal", () => {
    const revision = JSON.parse(config.define["import.meta.env.VITE_BUILD_REVISION"]);
    expect(typeof revision).toBe("string");
    // a spec run is no builder: the revision has to read as unstamped
    expect(revision).toBe("dev");
  });

  it("reads the file next to the frontend directory", () => {
    // ../VERSION relative to the config: the repository root on a checkout,
    // /VERSION in the nginx compile image, /opt/mrmap/VERSION in the
    // frontend-tests container. This spec sits beside the config, and under
    // vitest both module URLs are served through the same /@fs/ mapping, so
    // the very same resolution proves the rule.
    const expected = decodeURIComponent(
      new URL("../VERSION", import.meta.url).pathname).replace(/^\/@fs/, "");
    expect(CANONICAL_VERSION_FILE).toBe(expected);
    expect(CANONICAL_VERSION_FILE.endsWith("/VERSION")).toBe(true);
  });

  it("accepts the grammar releases are written in", () => {
    expect(SEMVER_STRICT.test("0.2.0-rc.1+9f8e7d6")).toBe(true);
    expect(SEMVER_STRICT.test("1.0.0-alpha.1")).toBe(true);
  });

  it("refuses versions no build may carry", () => {
    for (const invalid of ["", "v1.2.3", "1.2", "01.2.3", "1.2.3-", "nope"]) {
      expect(SEMVER_STRICT.test(invalid), invalid).toBe(false);
    }
  });

});
