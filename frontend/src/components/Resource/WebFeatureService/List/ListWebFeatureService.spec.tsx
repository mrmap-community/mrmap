import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { serviceListProps } from "../../Generic/ServiceList/serviceListProps";
import ListWebFeatureService, { WFS_SERVICE_LIST_CONFIG, WEB_FEATURE_SERVICE_LIST_FIELDS } from "./ListWebFeatureService";

const state = vi.hoisted(() => ({ props: undefined as Record<string, unknown> | undefined }));
vi.mock("../../../../jsonapi/components/ListGuesser", () => ({ default: (props: Record<string, unknown>) => { state.props = props; return null; } }));
beforeEach(() => { state.props = undefined; });

describe("ListWebFeatureService", () => {
  it("uses the shared service table, header and detail aside", () => {
    render(<ListWebFeatureService />);
    expect(state.props?.header).toBeDefined();
    expect(state.props?.columns).toBeDefined();
    expect(state.props?.aside).toBeDefined();
    expect(state.props?.perPage).toBe(25);
    expect(state.props?.sort).toEqual({ field: "title", order: "ASC" });
  });
  it("keeps search and alert filters always available", () => {
    const props = serviceListProps(WFS_SERVICE_LIST_CONFIG);
    expect(props.additionalFilters?.map(filter => filter.props)).toEqual([
      { source: "search", alwaysOn: true }, { source: "has_alert", alwaysOn: true },
    ]);
  });
  it("requests the configured API fieldset and protocol", () => {
    render(<ListWebFeatureService />);
    expect(state.props?.queryOptions).toEqual({
      meta: { jsonApiParams: { ["fields[" + WFS_SERVICE_LIST_CONFIG.resource + "]"]: WEB_FEATURE_SERVICE_LIST_FIELDS.join(",") } },
    });
    expect(WFS_SERVICE_LIST_CONFIG).toMatchObject({ protocol: "WFS", countLabelKey: "featureTypes" });
    expect(WEB_FEATURE_SERVICE_LIST_FIELDS).toEqual(expect.arrayContaining(["id", "title", "abstract", "has_alert", "element_count"]));
    expect(WEB_FEATURE_SERVICE_LIST_FIELDS).not.toContain("xml");
  });
  it("asks only the attributes the wfs screen answers", () => {
    // the shared presentation of the screens of services
    expect(WEB_FEATURE_SERVICE_LIST_FIELDS).toEqual(
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
    // the feature types and the authenticated preview are answered by a web
    // feature service itself
    expect(WEB_FEATURE_SERVICE_LIST_FIELDS).toEqual(
      expect.arrayContaining(["featuretypes", "preview_url"]),
    );
    // no attribute of a web map service or of a catalogue is copied into the
    // request of a web feature service
    expect(WEB_FEATURE_SERVICE_LIST_FIELDS).not.toContain("layers");
    expect(WEB_FEATURE_SERVICE_LIST_FIELDS).not.toContain("is_secured");
    expect(WEB_FEATURE_SERVICE_LIST_FIELDS).not.toContain(
      "xml_backup_file_secured",
    );
    expect(WEB_FEATURE_SERVICE_LIST_FIELDS).not.toContain("harvest_aborted");
    expect(WEB_FEATURE_SERVICE_LIST_FIELDS).not.toContain(
      "running_harvesting_job",
    );
  });

});
