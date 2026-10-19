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
    // the states are named as the api filters them, which is the source of the
    // filter which the filter button of the list offers for the same state
    expect(facetOf({ has_alert: true })).toEqual("needsAttention");
    // a filter which comes from the url answers a boolean as a string
    expect(facetOf({ has_alert: "false" })).toEqual("healthy");
    expect(facetOf({ monitoring_failed: true })).toEqual("monitoringFailed");
    expect(facetOf({ update_failed: true })).toEqual("updateFailed");
    expect(facetOf({ update_review_required: true })).toEqual(
      "updateReviewRequired",
    );
  });

  it("keeps every filter which is not a facet when a facet is chosen", () => {
    expect(
      filterForFacet(
        {
          search: "soil",
          title__icontains: "soil",
          bbox_lat_lon__intersects: "POLYGON((6 49,7 49,7 50,6 50,6 49))",
          has_alert: true,
        },
        "updateFailed",
      ),
    ).toEqual({
      search: "soil",
      title__icontains: "soil",
      bbox_lat_lon__intersects: "POLYGON((6 49,7 49,7 50,6 50,6 49))",
      update_failed: true,
    });
  });

  it("resets every filter with the facet of all services", () => {
    // all is no narrowing at all, so it answers the whole list - the search and
    // the filters of the filter button included
    expect(
      filterForFacet(
        { search: "soil", title__icontains: "soil", has_alert: true },
        "all",
      ),
    ).toEqual({});
    // a facet never answers two states of attention at once
    expect(
      filterForFacet(
        { has_alert: true, monitoring_failed: true },
        "updateReviewRequired",
      ),
    ).toEqual({ update_review_required: true });
  });

  it("leaves the filter of the list itself out of a facet", () => {
    // the list applies it on its own, so a facet which carries it would ask for
    // services which are update candidates of another service
    expect(
      filterForFacet({ is_update_candidate: false, search: "soil" }, "healthy"),
    ).toEqual({ search: "soil", has_alert: false });
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
        has_alert: true,
        monitoring_failed_at: "2026-10-01T10:00:00Z",
        is_update_candidate: false,
      }),
    ).toEqual({ search: "soil" });
  });
});
