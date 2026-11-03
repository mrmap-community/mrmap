import { describe, expect, it } from "vitest";

import RESOURCES from "./Definition";

interface ListOptions {
  aside?: unknown;
  sparseFieldsets?: { type: string; fields: string[] }[];
}

const listOptionsOf = (name: string): ListOptions | undefined =>
  (RESOURCES.find((resource) => resource.name === name)?.options as { list?: ListOptions } | undefined)?.list;

/**
 * The screens which list the elements of a service offer the map viewer of the element their user
 * clicked beside their rows, and that button opens the service which owns the element. The service is
 * no column of these screens, so the list only answers it when its sparse fieldset names it - without
 * it the button beside the selection has no service to open.
 */
describe("the resource definitions of the screens which offer their selection in the map viewer", () => {
  it.each(["Layer", "FeatureType"])("%s asks for the viewer button of its aside", (name) => {
    const list = listOptionsOf(name);
    expect(list?.aside).toBeDefined();
    const fieldset = list?.sparseFieldsets?.find((fields) => fields.type === name);
    expect(fieldset?.fields).toContain("service");
  });

  it("names the columns of its rows in that fieldset too", () => {
    // the request which answers a page goes out before the grid registered its columns, so the
    // rows of a first visit are only answered when the fieldset names their columns itself
    for (const name of ["Layer", "FeatureType"]) {
      const fields = listOptionsOf(name)?.sparseFieldsets?.find((set) => set.type === name)?.fields;
      expect(fields).toEqual(expect.arrayContaining(["id", "title", "abstract", "string_representation"]));
    }
  });
});
