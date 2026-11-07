import { describe, expect, it } from "vitest";

import RESOURCES from "../Definition";
import ListCatalogueServiceUpdateJob from "./ListCatalogueServiceUpdateJob";
import ShowCatalogueServiceUpdateJob from "./ShowCatalogueServiceUpdateJob";

describe("catalogue update job resources", () => {
  it("registers the list and the show screen the menu and the alerts lead to", () => {
    const entry = RESOURCES.find(
      ({ name }) => name === "CatalogueServiceUpdateJob",
    );
    expect(entry?.list).toBe(ListCatalogueServiceUpdateJob);
    expect(entry?.show).toBe(ShowCatalogueServiceUpdateJob);
    // the menu entry says what it lists, in both languages, through the key
    expect(entry?.options?.label).toBe(
      "resources.CatalogueServiceUpdateJob.name",
    );
    // the CSW group keeps its place: catalogues, runs, schedules, update jobs
    expect(entry?.options?.menu).toEqual({ group: "CSW", order: 40 });
  });
});
