import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ListWithDialogs from "../../../jsonapi/components/ListWithDialogs";
import ListBackgroundProcess, {
  ACTIVE_STATUSES,
} from "./ListBackgroundProcess";

const state = vi.hoisted(() => ({
  /** the props the overview hands to the list, ReadyState.CONNECTING is 0 */
  ready: 0,
}));

vi.mock("../../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ realtimeIsReady: state.ready }),
}));

vi.mock("../../../jsonapi/components/ListWithDialogs", () => ({
  default: vi.fn(() => null),
}));

const listProps = () =>
  vi.mocked(ListWithDialogs).mock.calls.at(-1)?.[0].listGuesserProps;

beforeEach(() => {
  state.ready = 0;
});

describe("ListBackgroundProcess", () => {
  // the EDIT button of a row navigates to /BackgroundProcess/<id>, which is the
  // route the dialogs of ListWithDialogs answer. A list on its own keeps
  // answering that route with the list itself and offers an action without an
  // editor (#1275)
  it("keeps the edit dialog of a process beside its list", () => {
    render(<ListBackgroundProcess />);
    expect(vi.mocked(ListWithDialogs)).toHaveBeenCalledOnce();
  });

  it("starts the overview with the processes which did not end yet, newest first", () => {
    render(<ListBackgroundProcess />);
    expect(listProps()?.filterDefaultValues).toEqual({
      status: ACTIVE_STATUSES,
    });
    expect(ACTIVE_STATUSES).toEqual("pending,running");
    expect(listProps()?.sort).toEqual({ field: "dateCreated", order: "DESC" });
    expect(listProps()?.perPage).toEqual(25);
  });

  it("shows what a process reports about, how far it is and how far it came", () => {
    render(<ListBackgroundProcess />);
    expect(listProps()?.defaultSelectedColumns).toEqual([
      "description",
      "processType",
      "phase",
      "status",
      "progress",
      "dateCreated",
      "doneAt",
      "duration",
      "relatedResource",
      "actions",
    ]);
    const sources = (
      listProps()?.updateFieldDefinitions ?? []
    ).map((definition) => definition.props.source);
    expect(sources).toContain("status");
    expect(sources).toContain("relatedResource");
    expect(sources).toContain("duration");
  });

  it("falls back to polling only while the realtime bus is not connected", () => {
    render(<ListBackgroundProcess />);
    expect(listProps()?.refetchInterval).toEqual(20000);
    // ReadyState.OPEN is 1
    state.ready = 1;
    render(<ListBackgroundProcess />);
    expect(listProps()?.refetchInterval).toEqual(false);
  });
});
