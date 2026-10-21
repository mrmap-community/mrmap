import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ServiceListConfig } from "../Generic/ServiceList/config";
import CatalogueServiceList, {
  CATALOGUE_SERVICE_LIST_FIELDS,
  HarvestButton,
} from "./CatalogueServiceList";

const state = vi.hoisted(() => ({
  /** the props the screen hands to the list with the dialog routes */
  props: undefined as Record<string, unknown> | undefined,
}));

// the create and edit dialogs of the resource are routed by the ListWithDialogs
vi.mock("../../../jsonapi/components/ListWithDialogs", () => ({
  default: (props: Record<string, unknown>) => {
    state.props = props;
    return null;
  },
}));

beforeEach(() => {
  state.props = undefined;
});

const listGuesserProps = () =>
  state.props?.listGuesserProps as Record<string, unknown> & {
    queryOptions: { meta: { jsonApiParams: Record<string, string> } };
    listContent: { props: { config: ServiceListConfig } };
  };

describe("CatalogueServiceList", () => {
  it("keeps the dialog routes of the resource beside the screen of services", () => {
    render(<CatalogueServiceList />);
    // the screen is rendered by the ListWithDialogs and not by a bare list, so
    // the routes of the create and edit dialogs stay registered
    expect(state.props).toBeDefined();
    expect(listGuesserProps().listContent).toBeDefined();
    expect(listGuesserProps().perPage).toEqual(25);
    expect(listGuesserProps().sort).toEqual({ field: "title", order: "ASC" });
    expect(listGuesserProps().aside).toEqual(false);
    // the screen of services replaces the datagrid of the generic list, so the
    // harvesting is not offered by an additional action of that datagrid - it
    // is offered per row by the configuration of the screen
    expect(listGuesserProps().additionalActions).toBeUndefined();
    // the list of catalogues introduces no filter of its own - and especially
    // not the filter of the update candidates, which only the lists of web map
    // services and of web feature services answer
    expect(listGuesserProps().filter).toBeUndefined();
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
      ]),
    );
    // no attribute of a web map service or of a web feature service is copied
    // into the request of a catalogue
    expect(CATALOGUE_SERVICE_LIST_FIELDS).not.toContain("layers");
    expect(CATALOGUE_SERVICE_LIST_FIELDS).not.toContain("featuretypes");
    expect(CATALOGUE_SERVICE_LIST_FIELDS).not.toContain("is_secured");
    expect(CATALOGUE_SERVICE_LIST_FIELDS).not.toContain("preview_url");
  });

  it("asks the attributes by the options of the query, which reach the request", () => {
    render(<CatalogueServiceList />);
    // the key names the resource of this list and no other
    expect(
      Object.keys(listGuesserProps().queryOptions.meta.jsonApiParams),
    ).toEqual(["fields[CatalogueService]"]);
    expect(
      listGuesserProps().queryOptions.meta.jsonApiParams[
        "fields[CatalogueService]"
      ],
    ).toEqual(CATALOGUE_SERVICE_LIST_FIELDS.join(","));
  });

  it("counts the records of a catalogue with the csw details and its harvest button", () => {
    render(<CatalogueServiceList />);
    const config = listGuesserProps().listContent.props.config;
    expect(config.resource).toEqual("CatalogueService");
    expect(config.protocol).toEqual("CSW");
    expect(config.countLabelKey).toEqual("records");
    // the records of a catalogue are not answered within its records, so the
    // count of them is answered by the annotation of the page alone
    expect(config.countRelation).toBeUndefined();
    // the harvest button stays exported for its other consumers and is offered
    // per row through the shared action slot
    expect(config.RowAction).toBe(HarvestButton);
  });
});
