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
        "lastModifiedAt",
        "isSecured",
        "xmlBackupFileSecured",
      ]),
    );
    // the api annotates a state of attention only for a request which names it
    expect(WEB_MAP_SERVICE_LIST_FIELDS).toEqual(
      expect.arrayContaining([
        "hasAlert",
        "monitoringFailed",
        "monitoringFailedAt",
        "updateReviewRequired",
        "updateReviewRequiredAt",
        "updateFailed",
        "updateFailedAt",
      ]),
    );
    // the capabilities of a service are stored as text and are not part of a row
    expect(WEB_MAP_SERVICE_LIST_FIELDS).not.toContain("xml");
  });
});
