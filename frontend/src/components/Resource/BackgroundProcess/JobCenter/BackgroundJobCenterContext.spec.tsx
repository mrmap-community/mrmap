import type { BackgroundJobRecord } from "./jobStore";

import { useEffect } from "react";

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
    total: undefined as number | undefined,
    refetch: vi.fn(),
  },
  terminal: {
    data: [] as BackgroundJobRecord[],
    isPending: false,
    error: null as Error | null,
    total: undefined as number | undefined,
    refetch: vi.fn(),
  },
  authenticated: true,
  subscriptions: new Map<string, Set<Handler>>(),
  // the topics the provider asked the dataProvider to (un)subscribe: the
  // counting specs below assert the frames a progression costs (#1462)
  subscribeCalls: [] as string[],
  unsubscribeCalls: [] as string[],
  notify: vi.fn(),
  // the batches the failure seam reported to its subscribers (#1461)
  failures: [] as string[][],
  // stable identities: the provider folds `translate` into `ingest` and the
  // hydrate effects depend on `ingest` - a fresh function per render would
  // (rightfully) rebuild the store over and over
  translate: (key: string) => key,
}));

// the dataProvider object is created once and returned with one identity:
// react-admin's hook hands out the stable context value, and the counting
// specs below only measure what the provider under test asks for
vi.mock("react-admin", () => {
  const provider = {
    subscribe: (topic: string, handler: Handler) => {
      state.subscribeCalls.push(topic);
      const handlers = state.subscriptions.get(topic) ?? new Set();
      handlers.add(handler);
      state.subscriptions.set(topic, handlers);
    },
    unsubscribe: (topic: string, handler: Handler) => {
      state.unsubscribeCalls.push(topic);
      state.subscriptions.get(topic)?.delete(handler);
    },
  };
  return {
    useAuthState: () => ({ authenticated: state.authenticated }),
    useDataProvider: () => provider,
    useGetList: (_resource: string, params: { filter: { status: string } }) =>
      params.filter.status === "pending,running"
        ? state.active
        : state.terminal,
    useNotify: () => state.notify,
    useTranslate: () => state.translate,
  };
});

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

/** reads what the compact table of the dashboard reads: the two windows with
 *  the outcome of their reads, their totals and whether there is a session
 *  which may ask at all (#1815) */
const WindowProbe = () => {
  const { windows, totals, hydrated } = useBackgroundJobCenter();
  return (
    <span data-testid="windows">
      {JSON.stringify({
        hydrated,
        active: windows.active,
        recent: windows.recent,
        totals,
      })}
    </span>
  );
};

/** the answer of the provider about the two windows it hydrates from */
const windowsAnswer = () =>
  JSON.parse(screen.getByTestId("windows").textContent ?? "{}");

/** registers on the failure seam (#1461) and records every batch it is told */
const FailureProbe = () => {
  const { subscribeFailed } = useBackgroundJobCenter();
  useEffect(
    () =>
      subscribeFailed((records) => {
        state.failures.push(records.map((record) => String(record.id)));
      }),
    [subscribeFailed],
  );
  return null;
};

const rendered = () => screen.getByTestId("probe").textContent;

beforeEach(() => {
  state.ready = 1;
  state.authenticated = true;
  state.active = {
    data: [],
    isPending: false,
    error: null,
    total: undefined,
    refetch: vi.fn(),
  };
  state.terminal = {
    data: [],
    isPending: false,
    error: null,
    total: undefined,
    refetch: vi.fn(),
  };
  state.subscriptions = new Map();
  state.subscribeCalls = [];
  state.unsubscribeCalls = [];
  state.failures = [];
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

  it("sends no subscription frame for progress events of the same active set", () => {
    state.active.data = [job({ id: 1 }), job({ id: 2 })];
    render(
      <BackgroundJobCenterProvider>
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    // the watched set is in place; from here on the counting starts clean
    expect([...state.subscribeCalls].sort()).toEqual([
      "resource/BackgroundProcess",
      "resource/BackgroundProcess/1",
      "resource/BackgroundProcess/2",
    ]);
    state.subscribeCalls = [];
    state.unsubscribeCalls = [];
    // two ingestions of the same active set: progress only, no membership
    // change - the frame count for this must be zero (#1462)
    emit("resource/BackgroundProcess/1", {
      type: "updated",
      payload: { records: [job({ id: 1, progress: 30 })] },
    });
    emit("resource/BackgroundProcess/2", {
      type: "updated",
      payload: { records: [job({ id: 2, progress: 40 })] },
    });
    expect(state.subscribeCalls).toEqual([]);
    expect(state.unsubscribeCalls).toEqual([]);
    // and the store still took the progress
    expect(rendered()).toBe("1,2");
  });

  it("answers a changed active set with its delta only", () => {
    state.active.data = [job({ id: 1 }), job({ id: 2 })];
    render(
      <BackgroundJobCenterProvider>
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    state.subscribeCalls = [];
    state.unsubscribeCalls = [];
    // job 1 completes: only its own topic goes away, job 2 keeps its
    // subscription untouched
    emit("resource/BackgroundProcess/1", {
      type: "updated",
      payload: {
        records: [job({ id: 1, status: "completed", state: "completed" })],
      },
    });
    expect(state.unsubscribeCalls).toEqual(["resource/BackgroundProcess/1"]);
    expect(state.subscribeCalls).toEqual([]);
    // a newly created active process arrives on its own topic - and the
    // already watched ones are not resubscribed for it
    emit("resource/BackgroundProcess", {
      type: "created",
      payload: { records: [job({ id: 3 })] },
    });
    expect(state.subscribeCalls).toEqual(["resource/BackgroundProcess/3"]);
    expect(state.unsubscribeCalls).toEqual(["resource/BackgroundProcess/1"]);
    expect(rendered()).toBe("1,2,3");
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

  it("reports live failures to the failure seam and nothing for a hydration replay", () => {
    // the recovered failure is history: the store shows it, the seam stays
    // silent - a reload must not re-tell failures the user did not watch
    state.active.data = [job({ id: 5, status: "failed", state: "failed" })];
    render(
      <BackgroundJobCenterProvider>
        <FailureProbe />
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    expect(rendered()).toBe("5");
    expect(state.failures).toEqual([]);
    // a live failure is told exactly once, however often its message arrives:
    // the store never lets a decided process move back (#1461)
    const failing = job({ id: 6, status: "failed", state: "failed" });
    emit("resource/BackgroundProcess", {
      type: "created",
      payload: { records: [failing] },
    });
    emit("resource/BackgroundProcess", {
      type: "created",
      payload: { records: [failing] },
    });
    expect(state.failures).toEqual([["6"]]);
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

  it("answers the dashboard with the two windows and the outcome of their reads", () => {
    // #1815: the compact table of the dashboard reads the windows and not only
    // the store, because a bounded store cannot tell an unread window from a
    // deployment without work
    state.active.data = [job({ id: 1 })];
    state.terminal.data = [
      job({ id: 5, status: "completed", state: "completed" }),
    ];
    state.active.total = 4;
    state.terminal.total = 40;
    render(
      <BackgroundJobCenterProvider>
        <WindowProbe />
      </BackgroundJobCenterProvider>,
    );
    const answer = windowsAnswer();
    expect(answer.hydrated).toBe(true);
    expect(answer.active.records.map((record: { id: number }) => record.id)).toEqual([1]);
    expect(answer.recent.records.map((record: { id: number }) => record.id)).toEqual([5]);
    // the totals are what tells a bounded view apart from the whole answer of
    // the api, so they travel with the windows
    expect(answer.totals).toEqual({ active: 4, recent: 40 });
  });

  it("answers the dashboard with the window it could not read", () => {
    // a read which is on its way and a read the api refused are both answered
    // as themselves: the card decides from them, the store cannot
    state.active.isPending = true;
    state.terminal.error = { status: 500 } as unknown as Error;
    render(
      <BackgroundJobCenterProvider>
        <WindowProbe />
      </BackgroundJobCenterProvider>,
    );
    const answer = windowsAnswer();
    expect(answer.active.isPending).toBe(true);
    expect(answer.active.records).toEqual([]);
    expect(answer.recent.isPending).toBe(false);
    // the error travels with the window, so the card can tell a broken api
    // apart from a refused read instead of reading an empty store
    expect(answer.recent.error).toEqual({ status: 500 });
    // totals of a read which never answered stay unanswered, so a card cannot
    // print a bounded number out of nothing
    expect(answer.totals.active).toBeUndefined();
    expect(answer.totals.recent).toBeUndefined();
  });

  it("answers that there is no session to ask with", () => {
    // #833: without a session the reads are never fired, so `isPending` of them
    // would never settle - `hydrated` is what says so and keeps a card from
    // hanging in "loading" forever
    state.authenticated = false;
    state.active.isPending = true;
    state.terminal.isPending = true;
    render(
      <BackgroundJobCenterProvider>
        <WindowProbe />
      </BackgroundJobCenterProvider>,
    );
    expect(windowsAnswer().hydrated).toBe(false);
  });

  it("polls both windows while the bus stays down", () => {
    // the reconnect above is the recovery, this is its floor: without a bus
    // nothing pushes, so the pages are read per interval (#1466)
    vi.useFakeTimers();
    state.ready = 0;
    render(
      <BackgroundJobCenterProvider>
        <Probe />
      </BackgroundJobCenterProvider>,
    );
    expect(state.active.refetch).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(20_000);
    });
    expect(state.active.refetch).toHaveBeenCalledTimes(1);
    expect(state.terminal.refetch).toHaveBeenCalledTimes(1);

    act(() => {
      vi.advanceTimersByTime(20_000);
    });
    expect(state.active.refetch).toHaveBeenCalledTimes(2);
    expect(state.terminal.refetch).toHaveBeenCalledTimes(2);
  });
});
