import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ServiceListConfig } from "../../Generic/ServiceList/config";
import ListWebFeatureService, {
  WEB_FEATURE_SERVICE_LIST_FIELDS,
} from "./ListWebFeatureService";

const state = vi.hoisted(() => ({
  /** the props the screen hands to the list with the dialog routes */
  props: undefined as Record<string, unknown> | undefined,
}));

// the create and edit dialogs of the resource are routed by the ListWithDialogs
vi.mock("../../../../jsonapi/components/ListWithDialogs", () => ({
  default: (props: Record<string, unknown>) => {
    state.props = props;
    return null;
  },
}));

beforeEach(() => {
  state.props = undefined;
});

describe("ListWebFeatureService", () => {
  it("keeps the dialog routes of the resource beside the screen of services", () => {
    render(<ListWebFeatureService />);
    // the screen is rendered by the ListWithDialogs and not by a bare list, so
    // the routes of the create and edit dialogs stay registered
    expect(state.props).toBeDefined();
    const listGuesserProps = state.props?.listGuesserProps as Record<
      string,
      unknown
    >;
    expect(listGuesserProps).toBeDefined();
    expect(listGuesserProps.listContent).toBeDefined();
    expect(listGuesserProps.perPage).toEqual(25);
    expect(listGuesserProps.sort).toEqual({ field: "title", order: "ASC" });
    expect(listGuesserProps.aside).toEqual(false);
    // a view without services is answered by the screen itself
    expect(
      (listGuesserProps.empty as { type: unknown } | undefined)?.type,
    ).toBe((listGuesserProps.listContent as { type: unknown }).type);
    // the list applies no filter of its own besides the one the generic list
    // already answers for web feature services
    expect(listGuesserProps.filter).toBeUndefined();
  });

  it("searches the services by what the api answers as filter", () => {
    render(<ListWebFeatureService />);
    const listGuesserProps = state.props?.listGuesserProps as {
      additionalFilters: { props: { source: string; alwaysOn?: boolean } }[];
    };
    expect(listGuesserProps.additionalFilters).toHaveLength(1);
    expect(listGuesserProps.additionalFilters[0].props.source).toEqual(
      "search",
    );
    expect(listGuesserProps.additionalFilters[0].props.alwaysOn).toEqual(true);
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

  it("asks the attributes by the options of the query, which reach the request", () => {
    render(<ListWebFeatureService />);
    const listGuesserProps = state.props?.listGuesserProps as {
      queryOptions: { meta: { jsonApiParams: Record<string, string> } };
    };
    // the key names the resource of this list and no other
    expect(
      Object.keys(listGuesserProps.queryOptions.meta.jsonApiParams),
    ).toEqual(["fields[WebFeatureService]"]);
    expect(
      listGuesserProps.queryOptions.meta.jsonApiParams[
        "fields[WebFeatureService]"
      ],
    ).toEqual(WEB_FEATURE_SERVICE_LIST_FIELDS.join(","));
  });

  it("counts the feature types of a web feature service with the wfs details", () => {
    render(<ListWebFeatureService />);
    const listGuesserProps = state.props?.listGuesserProps as {
      listContent: { props: { config: ServiceListConfig } };
    };
    const config = listGuesserProps.listContent.props.config;
    expect(config.resource).toEqual("WebFeatureService");
    expect(config.protocol).toEqual("WFS");
    expect(config.countLabelKey).toEqual("featureTypes");
    // the relationship the api really answers for a web feature service
    expect(config.countRelation).toEqual("featuretypes");
    // no row action is answered apart from the standard ones
    expect(config.RowAction).toBeUndefined();
  });
});
