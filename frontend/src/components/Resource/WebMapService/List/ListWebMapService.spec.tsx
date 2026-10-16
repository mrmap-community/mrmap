import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ListWebMapService, {
  WEB_MAP_SERVICE_LIST_FIELDS,
} from "./ListWebMapService";

const state = vi.hoisted(() => ({
  /** the props the screen hands to the list of the resource */
  props: undefined as Record<string, unknown> | undefined,
}));

vi.mock("../../../../jsonapi/components/ListGuesser", () => ({
  default: (props: Record<string, unknown>) => {
    state.props = props;
    return null;
  },
}));

beforeEach(() => {
  state.props = undefined;
});

describe("ListWebMapService", () => {
  it("shows the dedicated screen instead of a table of every column", () => {
    render(<ListWebMapService />);
    expect(state.props?.listContent).toBeDefined();
    expect((state.props?.listContent as { type: unknown }).type).toBeTypeOf(
      "function",
    );
    expect(state.props?.perPage).toEqual(25);
    expect(state.props?.sort).toEqual({ field: "title", order: "ASC" });
    // the details of a service are shown beside its row and not in a side card
    expect(state.props?.aside).toEqual(false);
    // a view without services is answered by the screen itself, so its facets
    // and its search stay usable when it narrows the list to none
    expect((state.props?.empty as { type: unknown } | undefined)?.type).toBe(
      (state.props?.listContent as { type: unknown }).type,
    );
  });

  it("searches the services by what the api answers as filter", () => {
    render(<ListWebMapService />);
    const filters = state.props?.additionalFilters as {
      props: { source: string; alwaysOn?: boolean };
    }[];
    expect(filters).toHaveLength(1);
    expect(filters[0].props.source).toEqual("search");
    expect(filters[0].props.alwaysOn).toEqual(true);
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

  it("asks the attributes by the options of the query, which reach the request", () => {
    render(<ListWebMapService />);
    // the attributes of a resource are a parameter of the request and not a prop
    // of the list: only the options of the query are given to the data provider
    const queryOptions = state.props?.queryOptions as {
      meta: { jsonApiParams: Record<string, string> };
    };
    expect(queryOptions.meta.jsonApiParams["fields[WebMapService]"]).toEqual(
      WEB_MAP_SERVICE_LIST_FIELDS.join(","),
    );
  });
});
