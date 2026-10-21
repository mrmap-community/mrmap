import { describe, expect, it } from "vitest";

import RESOURCES from "../Definition";
import ShowWebFeatureServiceUpdateJob from "./ShowWebFeatureServiceUpdateJob";

describe("WFS update resources", () => {
  it("registers the job review page and schema-backed mapping resource", () => {
    expect(
      RESOURCES.find(({ name }) => name === "WebFeatureServiceUpdateJob")?.show,
    ).toBe(ShowWebFeatureServiceUpdateJob);
    expect(
      RESOURCES.find(({ name }) => name === "FeatureTypeMapping"),
    ).toBeDefined();
  });
});
