import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ListBackgroundProcess, {
  ACTIVE_STATUSES,
} from "./ListBackgroundProcess";

const state = vi.hoisted(() => ({
  /** the props the overview hands to the list, ReadyState.CONNECTING is 0 */
  ready: 0,
  props: undefined as Record<string, unknown> | undefined,
}));

vi.mock("../../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ realtimeIsReady: state.ready }),
}));

vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: (props: Record<string, unknown>) => {
    state.props = props;
    return null;
  },
}));

beforeEach(() => {
  state.ready = 0;
  state.props = undefined;
});

describe("ListBackgroundProcess", () => {
  it("starts the overview with the processes which did not end yet, newest first", () => {
    render(<ListBackgroundProcess />);
    expect(state.props?.filterDefaultValues).toEqual({
      status: ACTIVE_STATUSES,
    });
    expect(ACTIVE_STATUSES).toEqual("pending,running");
    expect(state.props?.sort).toEqual({ field: "dateCreated", order: "DESC" });
    expect(state.props?.perPage).toEqual(25);
  });

  it("shows what a process reports about, how far it is and how far it came", () => {
    render(<ListBackgroundProcess />);
    expect(state.props?.defaultSelectedColumns).toEqual([
      "description",
      "processType",
      "phase",
      "status",
      "progress",
      "dateCreated",
      "relatedResource",
      "actions",
    ]);
    const sources = (
      state.props?.updateFieldDefinitions as { props: { source: string } }[]
    ).map((definition) => definition.props.source);
    expect(sources).toContain("status");
    expect(sources).toContain("relatedResource");
  });

  it("falls back to polling only while the realtime bus is not connected", () => {
    render(<ListBackgroundProcess />);
    expect(state.props?.refetchInterval).toEqual(20000);
    // ReadyState.OPEN is 1
    state.ready = 1;
    render(<ListBackgroundProcess />);
    expect(state.props?.refetchInterval).toEqual(false);
  });
});
