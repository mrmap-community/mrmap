import { MemoryRouter } from "react-router-dom";

import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { serviceListProps } from "../../Generic/ServiceList/serviceListProps";
import ListWebMapService, { WMS_SERVICE_LIST_CONFIG, WEB_MAP_SERVICE_LIST_FIELDS } from "./ListWebMapService";

const state = vi.hoisted(() => ({ props: undefined as Record<string, unknown> | undefined }));
vi.mock("../../../../jsonapi/components/ListGuesser", () => ({ default: (props: Record<string, unknown>) => { state.props = props; return null; } }));
beforeEach(() => { state.props = undefined; });

describe("ListWebMapService", () => {
  it("uses the shared service table, header and detail aside", () => {
    render(<ListWebMapService />, { wrapper: MemoryRouter });
    expect(state.props?.header).toBeDefined();
    expect(state.props?.columns).toBeDefined();
    expect(state.props?.aside).toBeDefined();
    expect(state.props?.perPage).toBe(25);
    expect(state.props?.sort).toEqual({ field: "title", order: "ASC" });
  });
  it("keeps search and alert filters always available", () => {
    const props = serviceListProps(WMS_SERVICE_LIST_CONFIG);
    expect(props.additionalFilters?.map(filter => filter.props)).toEqual([
      { source: "search", alwaysOn: true }, { source: "has_alert", alwaysOn: true },
    ]);
  });
  it("requests the configured API fieldset and protocol", () => {
    render(<ListWebMapService />, { wrapper: MemoryRouter });
    expect(state.props?.queryOptions).toEqual({
      meta: { jsonApiParams: { ["fields[" + WMS_SERVICE_LIST_CONFIG.resource + "]"]: WEB_MAP_SERVICE_LIST_FIELDS.join(",") } },
    });
    expect(WMS_SERVICE_LIST_CONFIG).toMatchObject({ protocol: "WMS", countLabelKey: "layers" });
    expect(WEB_MAP_SERVICE_LIST_FIELDS).toEqual(expect.arrayContaining(["id", "title", "abstract", "has_alert", "element_count"]));
    expect(WEB_MAP_SERVICE_LIST_FIELDS).not.toContain("xml");
  });
  it("asks every attribute a row and the details of a service show", () => {
    expect(WEB_MAP_SERVICE_LIST_FIELDS).toEqual(
      expect.arrayContaining([
        "id",
        "title",
        "abstract",
        "hits",
        "last_modified_at",
        "is_secured",
        "xml_backup_file_secured",
      ]),
    );
    // the api annotates a state of attention only for a request which names it
    expect(WEB_MAP_SERVICE_LIST_FIELDS).toEqual(
      expect.arrayContaining([
        "has_alert",
        "monitoring_failed",
        "monitoring_failed_at",
        "update_review_required",
        "update_review_required_at",
        "update_failed",
        "update_failed_at",
      ]),
    );
    // the layers of a service are answered by the service itself, so a row asks
    // nothing for itself: the annotation counts them and the layers of the
    // service answer them, both only for a request which names them
    expect(WEB_MAP_SERVICE_LIST_FIELDS).toEqual(
      expect.arrayContaining(["element_count", "layers"]),
    );
    // the capabilities of a service are stored as text and are not part of a row
    expect(WEB_MAP_SERVICE_LIST_FIELDS).not.toContain("xml");
  });

});
