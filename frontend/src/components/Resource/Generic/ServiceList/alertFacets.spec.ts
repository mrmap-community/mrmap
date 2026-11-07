import { describe, expect, it } from "vitest";

import {
  ALERT_FILTER_KEYS,
  facetsFor,
  facetOf,
  filterForFacet,
  queryOfList,
  STATUS_FACETS,
  withoutAlertKeys,
  withoutFacetKeys,
} from "./alertFacets";

/** the filters of the harvesting which the filterset of a catalogue declares
 *  (registry/filters/service.py) - what a screen gives its config */
const CATALOGUE_HARVEST_FILTERS = ["harvest_aborted", "harvest_incomplete"];

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
    expect(facetOf({ has_alert: "false" })).toEqual("noAlerts");
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
      filterForFacet({ is_update_candidate: false, search: "soil" }, "noAlerts"),
    ).toEqual({ search: "soil", has_alert: false });
  });

  it("answers every facet by a filter the api understands", () => {
    // the facet without an alert is named by the state the api answers and not by
    // a health, which no answer of has_alert proves
    expect(STATUS_FACETS.map((facet) => facet.key)).toEqual([
      "all",
      "needsAttention",
      "noAlerts",
      "monitoringFailed",
      "updateFailed",
      "updateReviewRequired",
    ]);
  });

  it("answers the facets of the harvesting only for the resource which declares them", () => {
    // a screen gives the filters of the harvesting which its resource declares -
    // a kind of service which is not harvested declares none of them and gets no
    // facet of the harvesting, because the api ignores a filter its filterset
    // does not declare and answers the whole list for it
    expect(facetsFor().map((facet) => facet.key)).toEqual(
      STATUS_FACETS.map((facet) => facet.key),
    );
    expect(
      facetsFor(CATALOGUE_HARVEST_FILTERS).map((facet) => facet.key),
    ).toEqual([
      ...STATUS_FACETS.map((facet) => facet.key),
      "harvestAborted",
      "harvestIncomplete",
    ]);

    // every facet of a screen is a filter that screen's filterset declares, and
    // never a key the api would ignore
    for (const facet of facetsFor(CATALOGUE_HARVEST_FILTERS)) {
      for (const key of Object.keys(facet.filter ?? {})) {
        expect(
          key === "has_alert" ||
            key === "monitoring_failed" ||
            key === "update_failed" ||
            key === "update_review_required" ||
            CATALOGUE_HARVEST_FILTERS.includes(key),
        ).toBe(true);
      }
    }

    // a resource which declares one state of the harvesting and not the other is
    // narrowed by exactly that one
    expect(
      facetsFor(["harvest_aborted"]).map((facet) => facet.key),
    ).toEqual([...STATUS_FACETS.map((facet) => facet.key), "harvestAborted"]);
  });

  it("lights and narrows the facet of a harvesting which ended badly", () => {
    const catalogueFacets = facetsFor(CATALOGUE_HARVEST_FILTERS);
    expect(
      facetOf({ harvest_aborted: true }, catalogueFacets),
    ).toEqual("harvestAborted");
    expect(
      facetOf({ harvest_incomplete: "true" }, catalogueFacets),
    ).toEqual("harvestIncomplete");
    // a facet of another resource is not lit here: the list answers what the rows
    // of this screen answer
    expect(facetOf({ harvest_aborted: true })).toEqual("all");

    // the chosen facet replaces the states of attention and keeps the search, and
    // it asks the filter the filterset of a catalogue declares
    expect(
      filterForFacet(
        { search: "soil", has_alert: true, title__icontains: "soil" },
        "harvestAborted",
        catalogueFacets,
      ),
    ).toEqual({
      search: "soil",
      title__icontains: "soil",
      harvest_aborted: true,
    });
    // and the same key asked of a screen which does not offer it hands no filter
    // of the harvesting to the api at all
    expect(filterForFacet({ search: "soil" }, "harvestAborted")).toEqual({
      search: "soil",
    });
  });

  it("keeps the query of the list with the tiles of a state", () => {
    // the tiles count the services the list answers, so the filter the list
    // applies on its own belongs to the scope of a tile - only the states of
    // attention are replaced by the state of the tile itself, and the states of
    // the harvesting are states of attention like the others
    expect(
      withoutAlertKeys({
        search: "soil",
        is_update_candidate: false,
        has_alert: true,
        monitoring_failed_at: "2026-10-01T10:00:00Z",
        harvest_aborted: true,
        harvest_incomplete: false,
      }),
    ).toEqual({ search: "soil", is_update_candidate: false });
    // the facets, the tiles and the filter which the filter button offers name
    // one state each, and every one of those states is replaced here
    expect(ALERT_FILTER_KEYS).toEqual(
      expect.arrayContaining([
        "has_alert",
        "monitoring_failed",
        "update_failed",
        "update_review_required",
        "harvest_aborted",
        "harvest_incomplete",
      ]),
    );
  });

  it("merges the filters a user chose with the filter of the list itself", () => {
    // the list controller answers the permanent filter and the stored filters
    // apart, so what a list answers is only the merge of both
    expect(
      queryOfList({ is_update_candidate: false }, { search: "soil" }),
    ).toEqual({ search: "soil", is_update_candidate: false });
    // the filter of the list wins, because a user cannot lift it
    expect(
      queryOfList({ is_update_candidate: false }, { is_update_candidate: true }),
    ).toEqual({ is_update_candidate: false });
  });

  it("drops the filter of the list itself out of a facet", () => {
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
