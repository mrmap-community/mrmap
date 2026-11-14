import { act, render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useGetList } from "react-admin";

import IncidentCenterProvider, {
  INCIDENT_REALTIME_TOPIC,
  useIncidentCenter,
} from "./IncidentCenterContext";

type Handler = () => void;

const state = vi.hoisted(() => ({
  subscriptions: new Map<string, Set<Handler>>(),
  activeRefetch: vi.fn(),
  resolvedRefetch: vi.fn(),
}));

// the mocked window stands in for the react-query result: the spec pins
// WHICH queries the provider registers - that is the bounded-cadence
// contract - while the poll lifecycle itself belongs to react-query, which
// ends it when the consuming component unmounts
const windowOf = (refetch: ReturnType<typeof vi.fn>) => ({
  data: [],
  total: 0,
  isPending: false,
  error: null,
  refetch,
});

vi.mock("react-admin", () => ({
  useDataProvider: () => ({
    subscribe: (topic: string, handler: Handler) => {
      const handlers = state.subscriptions.get(topic) ?? new Set();
      handlers.add(handler);
      state.subscriptions.set(topic, handlers);
      return Promise.resolve({ data: null });
    },
    unsubscribe: (topic: string, handler: Handler) => {
      state.subscriptions.get(topic)?.delete(handler);
      return Promise.resolve({ data: null });
    },
  }),
  useGetList: vi.fn(),
}));

// the drawer is a consumer of the same context and has its own spec; here it
// would only re-render the whole shell for queries this spec does not make
vi.mock("./IncidentCenterDrawer", () => ({ default: () => null }));

const Probe = () => {
  const { open, setOpen } = useIncidentCenter();
  return <button onClick={() => setOpen(true)} aria-label={`open:${open}`} />;
};

const mockedUseGetList = vi.mocked(useGetList);

const providerTree = (
  <>
    <IncidentCenterProvider>
      <Probe />
    </IncidentCenterProvider>
  </>
);

beforeEach(() => {
  state.subscriptions = new Map();
  state.activeRefetch = vi.fn();
  state.resolvedRefetch = vi.fn();
  mockedUseGetList.mockReset();
  // first call answers the active window, second the resolved one - the
  // provider's useGetList order is what the query assertions read
  mockedUseGetList
    .mockReturnValueOnce(windowOf(state.activeRefetch) as never)
    .mockReturnValueOnce(windowOf(state.resolvedRefetch) as never);
});

describe("IncidentCenterProvider", () => {
  it("registers the two windows of the incident api with a bounded cadence", () => {
    render(providerTree);
    const calls = mockedUseGetList.mock.calls;
    expect(calls).toHaveLength(2);
    // the active window asks for the attention-demanding states in one read,
    // so the badge and the drawer rows can never disagree (#1321); the
    // totals are the permitted ones, the client never counts
    expect(calls[0][0]).toBe("OperationalIncident");
    expect(calls[0][1]).toMatchObject({
      filter: { state: "retrying,stalled,failed" },
      sort: { field: "lastOccurrence", order: "DESC" },
      pagination: { page: 1, perPage: 25 },
    });
    // the resolved window answers the recoveries which left the active count
    expect(calls[1][0]).toBe("OperationalIncident");
    expect(calls[1][1]).toMatchObject({
      filter: { state: "resolved" },
    });
    // both read at the bounded distance and without retry storms on an api
    // which may not exist yet (#1319) - react-query ends the poll on unmount
    for (const call of calls) {
      expect(call[2]).toEqual({ refetchInterval: 20000, retry: false });
    }
  });

  it("refetches both windows when the bus reports an incident change", () => {
    render(providerTree);
    const handlers = state.subscriptions.get(INCIDENT_REALTIME_TOPIC);
    expect(handlers?.size).toBe(1);
    act(() => {
      handlers?.forEach((handler) => handler());
    });
    expect(state.activeRefetch).toHaveBeenCalledTimes(1);
    expect(state.resolvedRefetch).toHaveBeenCalledTimes(1);
  });

  it("leaves the incident topic on unmount", () => {
    const { unmount } = render(providerTree);
    expect(state.subscriptions.get(INCIDENT_REALTIME_TOPIC)?.size).toBe(1);
    unmount();
    expect(state.subscriptions.get(INCIDENT_REALTIME_TOPIC)?.size).toBe(0);
  });

  it("shares one open state with its consumers", () => {
    const { getByRole } = render(providerTree);
    const probe = getByRole("button");
    expect(probe.getAttribute("aria-label")).toBe("open:false");
    act(() => {
      probe.click();
    });
    expect(probe.getAttribute("aria-label")).toBe("open:true");
  });
});
