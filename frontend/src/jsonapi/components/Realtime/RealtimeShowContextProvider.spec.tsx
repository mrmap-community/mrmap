import type { CrudEvent } from "../../../providers/dataProvider";

import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RealtimeShowContextProvider from "./RealtimeShowContextProvider";

interface ShowRecord {
  id: number;
  title: string;
}

const state = vi.hoisted(() => ({
  resource: "Service",
  record: { id: 7, title: "controller" } as ShowRecord,
  isFetching: false,
  isPending: false,
  refetch: vi.fn(),
  callbacks: new Map<string, Set<(event: CrudEvent) => void>>(),
}));
const provider = vi.hoisted(() => ({
  subscribe: vi.fn((topic: string, callback: (event: CrudEvent) => void) => {
    const callbacks = state.callbacks.get(topic) ?? new Set();
    callbacks.add(callback);
    state.callbacks.set(topic, callbacks);
  }),
  unsubscribe: vi.fn((topic: string, callback: (event: CrudEvent) => void) =>
    state.callbacks.get(topic)?.delete(callback),
  ),
}));
vi.mock("react-admin", () => ({
  useResourceContext: () => state.resource,
  useShowController: () => ({
    resource: state.resource,
    record: state.record,
    isFetching: state.isFetching,
    isPending: state.isPending,
    refetch: state.refetch,
  }),
  useDataProvider: () => provider,
  ShowContextProvider: ({ value }: { value: { record?: ShowRecord } }) => (
    <output>{JSON.stringify(value.record?.title ?? null)}</output>
  ),
}));

const emit = (title: string) =>
  act(() => {
    state.callbacks
      .get("resource/Service/7")
      ?.forEach((callback) =>
        callback({
          type: "updated",
          payload: { ids: [7], records: [{ id: 7, title }] },
        }),
      );
  });

const shown = () => screen.getByRole("status").textContent;

beforeEach(() => {
  state.resource = "Service";
  state.record = { id: 7, title: "controller" };
  state.isFetching = false;
  state.isPending = false;
  state.callbacks.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("RealtimeShowContextProvider", () => {
  it("shows the record of the realtime bus", () => {
    render(<RealtimeShowContextProvider />);
    expect(shown()).toContain("controller");
    emit("first");
    expect(shown()).toContain("first");
    emit("second");
    expect(shown()).toContain("second");
  });

  it("keeps one subscription across events of the same record", () => {
    const { unmount } = render(<RealtimeShowContextProvider />);
    expect(provider.subscribe).toHaveBeenCalledTimes(1);
    expect(provider.subscribe).toHaveBeenCalledWith(
      "resource/Service/7",
      expect.any(Function),
    );
    // two ingestions of the same record - the subscription must not be
    // torn down and rebuilt for either of them (#1462)
    emit("first");
    emit("second");
    expect(provider.subscribe).toHaveBeenCalledTimes(1);
    expect(provider.unsubscribe).not.toHaveBeenCalled();
    // and the unmount pairs the very callback it subscribed with, the way
    // the dataProvider's identity match expects
    unmount();
    expect(provider.unsubscribe).toHaveBeenCalledTimes(1);
    expect(provider.unsubscribe).toHaveBeenCalledWith(
      "resource/Service/7",
      provider.subscribe.mock.calls[0][1],
    );
  });

  it("is not rebuilt by an event: the stale check keeps its schedule", () => {
    vi.useFakeTimers();
    const isStale = vi.fn(() => true);
    render(
      <RealtimeShowContextProvider
        isStaleCheckInterval={10}
        isStale={isStale}
      />,
    );
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    // this event used to resubscribe the topic AND restart the interval
    emit("first");
    expect(provider.subscribe).toHaveBeenCalledTimes(1);
    expect(provider.unsubscribe).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    // the tick arrives on the schedule of the original interval - an event
    // did not push it back (#1462)
    expect(state.refetch).toHaveBeenCalledTimes(1);
    expect(provider.subscribe).toHaveBeenCalledTimes(1);
  });

  it("hands the timestamp of the last event to the stale check", () => {
    vi.useFakeTimers();
    const mounted = Date.now();
    const isStale = vi.fn(() => false);
    render(
      <RealtimeShowContextProvider
        isStaleCheckInterval={10}
        isStale={isStale}
      />,
    );
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    emit("first");
    act(() => {
      vi.advanceTimersByTime(6000);
    });
    expect(isStale).toHaveBeenCalledTimes(1);
    expect(isStale).toHaveBeenCalledWith(mounted + 4000, state.record);
  });

  it("does not refetch while the controller is fetching", () => {
    vi.useFakeTimers();
    const isStale = vi.fn(() => true);
    render(
      <RealtimeShowContextProvider
        isStaleCheckInterval={10}
        isStale={isStale}
      />,
    );
    state.isFetching = true;
    emit("first"); // the re-render which carries the fetching flag
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    expect(state.refetch).not.toHaveBeenCalled();
    expect(isStale).not.toHaveBeenCalled();
    // and it asks again once the flag is gone - the check reads the current
    // values, not the ones the interval was built with
    state.isFetching = false;
    emit("second");
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    expect(state.refetch).toHaveBeenCalledTimes(1);
  });

  it("refuses to render without a resource", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    state.resource = undefined as unknown as string;
    expect(() => render(<RealtimeShowContextProvider />)).toThrow(
      "RealtimeShow requires a non-empty resource prop or context",
    );
    errorSpy.mockRestore();
  });
});
