import type { BackgroundJobRecord } from "./jobStore";

import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BackgroundJobCenterProvider, {
  useBackgroundJobCenter,
} from "./BackgroundJobCenterContext";

type Handler = (event: {
  type: string;
  payload: { records?: BackgroundJobRecord[]; ids?: (string | number)[] };
}) => void;

// ReadyState.OPEN is 1, ReadyState.CONNECTING is 0 - the mock answers the
// numbers directly so the spec does not need the websocket library itself
const state = vi.hoisted(() => ({
  ready: 1,
  active: {
    data: [] as BackgroundJobRecord[],
    isPending: false,
    error: null as Error | null,
    refetch: vi.fn(),
  },
  terminal: {
    data: [] as BackgroundJobRecord[],
    isPending: false,
    error: null as Error | null,
    refetch: vi.fn(),
  },
  subscriptions: new Map<string, Set<Handler>>(),
  notify: vi.fn(),
  // stable identities: the provider folds `translate` into `ingest` and the
  // hydrate effects depend on `ingest` - a fresh function per render would
  // (rightfully) rebuild the store over and over
  translate: (key: string) => key,
}));

vi.mock("react-admin", () => ({
  useDataProvider: () => ({
    subscribe: (topic: string, handler: Handler) => {
      const handlers = state.subscriptions.get(topic) ?? new Set();
      handlers.add(handler);
      state.subscriptions.set(topic, handlers);
    },
    unsubscribe: (topic: string, handler: Handler) => {
      state.subscriptions.get(topic)?.delete(handler);
    },
  }),
  useGetList: (_resource: string, params: { filter: { status: string } }) =>
    params.filter.status === "pending,running" ? state.active : state.terminal,
  useNotify: () => state.notify,
  useTranslate: () => state.translate,
}));

vi.mock("../../../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ realtimeIsReady: state.ready }),
}));

vi.mock("./JobCenterDrawer", () => ({ default: () => null }));

/** emits an event of the realtime bus onto every handler of the topic */
const emit = (topic: string, event: Parameters<Handler>[0]) => {
  act(() => {
    state.subscriptions.get(topic)?.forEach((handler) => handler(event));
  });
};

const job = (
  overrides: Partial<BackgroundJobRecord>,
): BackgroundJobRecord => ({
  id: 1,
  status: "running",
  state: "running",
  processType: "harvest",
  dateCreated: "2026-11-10T10:00:00Z",
  ...overrides,
});

const Probe = () => {
  const { state: store } = useBackgroundJobCenter();
  return (
    <span data-testid="probe">
      {Object.keys(store.jobs).sort().join(",")}
    </span>
  );
};

const rendered = () => screen.getByTestId("probe").textContent;

beforeEach(() => {
  state.ready = 1;
  state.active = {
    data: [],
    isPending: false,
    error: null,
    refetch: vi.fn(),
  };
  state.terminal = {
    data: [],
    isPending: false,
    error: null,
    refetch: vi.fn(),
  };
  state.subscriptions = new Map();
  state.notify = vi.fn();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("BackgroundJobCenterProvider", () => {
  it("hydrates the store from both api windows without announcing anything", () => {
    state.active.data = [job({ id: 1 })];
    state.terminal.data = [
      job({ id: 5, status: "completed", state: "completed" }),
    ];
    render(
      <BackgroundJobCenterProvider>
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    expect(rendered()).toBe("1,5");
    expect(state.notify).not.toHaveBeenCalled();
  });

  it("subscribes the active processes on their own topics", () => {
    state.active.data = [job({ id: 1 }), job({ id: 2 })];
    render(
      <BackgroundJobCenterProvider>
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    expect(state.subscriptions.has("resource/BackgroundProcess")).toBe(true);
    expect(
      state.subscriptions.has("resource/BackgroundProcess/1"),
    ).toBe(true);
    expect(
      state.subscriptions.has("resource/BackgroundProcess/2"),
    ).toBe(true);
  });

  it("announces a failure once, however often its message arrives", () => {
    render(
      <BackgroundJobCenterProvider>
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    const failed = job({
      id: 9,
      status: "failed",
      state: "failed",
      description: "broken job",
    });
    emit("resource/BackgroundProcess", {
      type: "created",
      payload: { records: [failed] },
    });
    emit("resource/BackgroundProcess", {
      type: "created",
      payload: { records: [failed] },
    });
    expect(state.notify).toHaveBeenCalledTimes(1);
    expect(state.notify).toHaveBeenCalledWith(
      "backgroundActivity.jobCenter.notifyFailed",
      expect.objectContaining({ type: "warning" }),
    );
  });

  it("aggregates a burst of completions into one message after the quiet moment", () => {
    vi.useFakeTimers();
    render(
      <BackgroundJobCenterProvider>
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    const completed = (id: number) =>
      job({ id, status: "completed", state: "completed" });
    emit("resource/BackgroundProcess", {
      type: "created",
      payload: { records: [completed(10)] },
    });
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    emit("resource/BackgroundProcess", {
      type: "created",
      payload: { records: [completed(11), completed(12)] },
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    // the quiet moment restarted with the second burst - nothing told yet
    expect(state.notify).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(state.notify).toHaveBeenCalledTimes(1);
    expect(state.notify).toHaveBeenCalledWith(
      "backgroundActivity.jobCenter.notifyCompleted",
      expect.objectContaining({
        type: "success",
        messageArgs: { count: 3, smart_count: 3 },
      }),
    );
  });

  it("drops a deleted process from the view", () => {
    state.active.data = [job({ id: 1 })];
    render(
      <BackgroundJobCenterProvider>
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    expect(rendered()).toBe("1");
    emit("resource/BackgroundProcess", {
      type: "deleted",
      payload: { ids: [1] },
    });
    expect(rendered()).toBe("");
  });

  it("re-reads the api windows when the realtime bus came up again", () => {
    state.ready = 0;
    const { rerender } = render(
      <BackgroundJobCenterProvider>
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    expect(state.active.refetch).not.toHaveBeenCalled();
    state.ready = 1;
    rerender(
      <BackgroundJobCenterProvider>
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    expect(state.active.refetch).toHaveBeenCalledTimes(1);
    expect(state.terminal.refetch).toHaveBeenCalledTimes(1);
  });
});
