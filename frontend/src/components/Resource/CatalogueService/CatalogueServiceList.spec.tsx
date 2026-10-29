import { MemoryRouter } from "react-router-dom";

import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { serviceListProps } from "../Generic/ServiceList/serviceListProps";
import CatalogueServiceList, { CATALOGUE_SERVICE_LIST_CONFIG, CATALOGUE_SERVICE_LIST_FIELDS } from "./CatalogueServiceList";

const state = vi.hoisted(() => ({ props: undefined as Record<string, unknown> | undefined }));
vi.mock("../../../jsonapi/components/ListGuesser", () => ({ default: (props: Record<string, unknown>) => { state.props = props; return null; } }));
beforeEach(() => { state.props = undefined; });

describe("CatalogueServiceList", () => {
  it("uses the shared service table, header and detail aside", () => {
    render(<CatalogueServiceList />, { wrapper: MemoryRouter });
    expect(state.props?.header).toBeDefined();
    expect(state.props?.columns).toBeDefined();
    expect(state.props?.aside).toBeDefined();
    expect(state.props?.perPage).toBe(25);
    expect(state.props?.sort).toEqual({ field: "title", order: "ASC" });
  });
  it("keeps search and alert filters always available", () => {
    const props = serviceListProps(CATALOGUE_SERVICE_LIST_CONFIG);
    expect(props.additionalFilters?.map(filter => filter.props)).toEqual([
      { source: "search", alwaysOn: true }, { source: "has_alert", alwaysOn: true },
    ]);
  });
  it("requests the configured API fieldset and protocol", () => {
    render(<CatalogueServiceList />, { wrapper: MemoryRouter });
    expect(state.props?.queryOptions).toEqual({
      meta: { jsonApiParams: { ["fields[" + CATALOGUE_SERVICE_LIST_CONFIG.resource + "]"]: CATALOGUE_SERVICE_LIST_FIELDS.join(",") } },
    });
    expect(CATALOGUE_SERVICE_LIST_CONFIG).toMatchObject({ protocol: "CSW", countLabelKey: "records" });
    expect(CATALOGUE_SERVICE_LIST_FIELDS).toEqual(expect.arrayContaining(["id", "title", "abstract", "has_alert", "element_count"]));
    expect(CATALOGUE_SERVICE_LIST_FIELDS).not.toContain("xml");
  });
  it("asks only the attributes the csw screen answers", () => {
    // the shared presentation of the screens of services
    expect(CATALOGUE_SERVICE_LIST_FIELDS).toEqual(
      expect.arrayContaining([
        "id",
        "title",
        "abstract",
        "string_representation",
        "hits",
        "last_modified_at",
        "has_alert",
        "monitoring_failed",
        "monitoring_failed_at",
        "update_review_required",
        "update_review_required_at",
        "update_failed",
        "update_failed_at",
        "element_count",
      ]),
    );
    // the states of the harvesting and the running harvesting job are answered
    // by a catalogue, so a failure of the harvesting is shown in the row
    expect(CATALOGUE_SERVICE_LIST_FIELDS).toEqual(
      expect.arrayContaining([
        "harvest_aborted",
        "harvest_incomplete",
        "harvest_failed_at",
        "running_harvesting_job",
        "is_harvestable",
        "periodic_harvesting_jobs",
      ]),
    );
    // no attribute of a web map service or of a web feature service is copied
    // into the request of a catalogue
    expect(CATALOGUE_SERVICE_LIST_FIELDS).not.toContain("layers");
    expect(CATALOGUE_SERVICE_LIST_FIELDS).not.toContain("featuretypes");
    expect(CATALOGUE_SERVICE_LIST_FIELDS).not.toContain("is_secured");
    expect(CATALOGUE_SERVICE_LIST_FIELDS).not.toContain("preview_url");
  });

});
