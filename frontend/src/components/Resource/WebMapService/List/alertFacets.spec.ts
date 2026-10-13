import { describe, expect, it } from "vitest";
import {
  facetOf,
  filterForFacet,
  STATUS_FACETS,
  withoutFacetKeys,
} from "./alertFacets";

describe("the facets of the list of services", () => {
  it("answers all for filters which do not narrow by attention", () => {
    expect(facetOf(undefined)).toEqual("all");
    expect(facetOf({ search: "soil", is_update_candidate: false })).toEqual(
      "all",
    );
  });

  it("answers the facet which the filters of the list narrow to", () => {
    expect(facetOf({ hasAlert: true })).toEqual("needsAttention");
    // a filter which comes from the url answers a boolean as a string
    expect(facetOf({ hasAlert: "false" })).toEqual("healthy");
    expect(facetOf({ monitoringFailed: true })).toEqual("monitoringFailed");
    expect(facetOf({ updateReviewRequired: true })).toEqual(
      "updateReviewRequired",
    );
  });

  it("keeps every filter which is not a facet when a facet is chosen", () => {
    expect(
      filterForFacet(
        { search: "soil", hasAlert: true, is_update_candidate: false },
        "updateFailed",
      ),
    ).toEqual({ search: "soil", updateFailed: true });
  });

  it("removes the facet which was chosen before", () => {
    expect(filterForFacet({ monitoringFailed: true }, "all")).toEqual({});
  });

  it("answers every facet by a filter the api understands", () => {
    expect(STATUS_FACETS.map((facet) => facet.key)).toEqual([
      "all",
      "needsAttention",
      "healthy",
      "monitoringFailed",
      "updateFailed",
      "updateReviewRequired",
    ]);
  });

  it("drops the states of attention from the scope of a tile", () => {
    expect(
      withoutFacetKeys({
        search: "soil",
        hasAlert: true,
        monitoringFailedAt: "2026-10-01T10:00:00Z",
        is_update_candidate: false,
      }),
    ).toEqual({ search: "soil" });
  });
});
