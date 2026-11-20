import { useDataProvider, useGetList } from "react-admin";

import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type OperationalIncidentRecord } from "../incidentContract";
import useContextualIncidents, {
  aboutRecord,
} from "./useContextualIncidents";

vi.mock("react-admin", () => ({
  useDataProvider: vi.fn(),
  useGetList: vi.fn(),
}));

/**
 * The bus and the two windows the hook is built on, kept as spies of the spec
 * so a test can push a bus event through and see which window answered.
 */
const state = vi.hoisted(() => ({
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
  refetch: { active: vi.fn(), resolved: vi.fn() },
}));

const incident = (
  overrides: Partial<OperationalIncidentRecord> & { id: string },
): OperationalIncidentRecord => ({
  code: "harvesting_run_all_records",
  source: "harvesting",
  severity: "warning",
  status: "active",
  scope: "resource",
  summary: "the endpoint did not answer",
  occurrenceCount: 1,
  firstOccurredAt: "2026-11-14T10:00:00Z",
  lastOccurredAt: "2026-11-14T10:00:00Z",
  affectedResource: { type: "HarvestingJob", id: "42" },
  ...overrides,
});

/** the two windows the hook reads, keyed by the `status` facet it filters on */
const windows = (
  active: OperationalIncidentRecord[],
  resolved: OperationalIncidentRecord[],
) => {
  vi.mocked(useDataProvider).mockReturnValue({
    subscribe: state.subscribe,
    unsubscribe: state.unsubscribe,
  } as unknown as ReturnType<typeof useDataProvider>);
  vi.mocked(useGetList).mockImplementation((_resource, params) => {
    const filter = (
      params as unknown as { filter: { status: string } }
    ).filter;
    const rows = filter.status === "resolved" ? resolved : active;
    return {
      data: rows,
      total: rows.length,
      isPending: false,
      error: null,
      // the spy of its own window, so a bus event is traceable to the query
      refetch:
        filter.status === "resolved"
          ? state.refetch.resolved
          : state.refetch.active,
    } as unknown as ReturnType<typeof useGetList>;
  });
};

describe("aboutRecord", () => {
  it("matches the type and id the api answered for the incident", () => {
    const record = incident({ id: "a" });
    expect(aboutRecord(record, "HarvestingJob", 42)).toBe(true);
    expect(aboutRecord(record, "HarvestingJob", "42")).toBe(true);
    // the type of an incident is exact: a job is not the service it harvested
    expect(aboutRecord(record, "WebMapService", 42)).toBe(false);
    expect(aboutRecord(record, "HarvestingJob", 7)).toBe(false);
    expect(aboutRecord(record, undefined, 42)).toBe(false);
  });

  it("never matches a system incident, which answers no resource", () => {
    const system = incident({
      id: "s",
      scope: "system",
      affectedResource: null,
    });
    expect(aboutRecord(system, "HarvestingJob", 42)).toBe(false);
  });
});

describe("useContextualIncidents", () => {
  it("keeps only the incidents about the record of the screen", () => {
    windows(
      [
        incident({ id: "a" }),
        incident({
          id: "b",
          affectedResource: { type: "HarvestingJob", id: "7" },
        }),
        incident({
          id: "c",
          affectedResource: { type: "WebMapService", id: "42" },
        }),
      ],
      [],
    );
    const { result } = renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: 42 }),
    );
    expect(result.current.active.map((r) => r.id)).toEqual(["a"]);
  });

  it("never surfaces a system incident or one about another record", () => {
    windows(
      [
        // every row here is one this reader may see - the list itself is
        // narrowed by visible_for_user - so only the identity match decides
        // what belongs on this page; a system incident names no resource
        incident({ id: "system", scope: "system", affectedResource: null }),
        incident({ id: "mine" }),
      ],
      [],
    );
    const { result } = renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: "42" }),
    );
    expect(result.current.active.map((r) => r.id)).toEqual(["mine"]);
  });

  it("draws one entry per incident though the window repeats it", () => {
    windows([incident({ id: "dup" }), incident({ id: "dup" })], []);
    const { result } = renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: 42 }),
    );
    expect(result.current.active).toHaveLength(1);
  });

  it("orders errors before warnings and the newest activity first", () => {
    windows(
      [
        incident({
          id: "warn-new",
          severity: "warning",
          lastOccurredAt: "2026-11-14T12:00:00Z",
        }),
        incident({
          id: "err-old",
          severity: "error",
          lastOccurredAt: "2026-11-14T09:00:00Z",
        }),
        incident({
          id: "warn-old",
          severity: "warning",
          lastOccurredAt: "2026-11-14T08:00:00Z",
        }),
      ],
      [],
    );
    const { result } = renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: 42 }),
    );
    expect(result.current.active.map((r) => r.id)).toEqual([
      "err-old",
      "warn-new",
      "warn-old",
    ]);
  });

  it("reports the resolved window about the record separately", () => {
    windows(
      [incident({ id: "active" })],
      [
        incident({
          id: "resolved",
          status: "resolved",
          resolvedAt: "2026-11-13T10:00:00Z",
        }),
        incident({
          id: "resolved-other",
          status: "resolved",
          affectedResource: { type: "HarvestingJob", id: "99" },
        }),
      ],
    );
    const { result } = renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: 42 }),
    );
    expect(result.current.active.map((r) => r.id)).toEqual(["active"]);
    expect(result.current.resolved.map((r) => r.id)).toEqual(["resolved"]);
  });

  it("asks the api with the one declared facet and never a target filter", () => {
    windows([], []);
    renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: 42 }),
    );
    const queries = vi.mocked(useGetList).mock.calls.map(([, params]) => params);
    for (const params of queries) {
      const filter = (
        params as unknown as { filter: Record<string, string> }
      ).filter;
      expect(Object.keys(filter)).toEqual(["status"]);
      expect(filter.status).toMatch(/^(active|resolved)$/);
    }
  });

  it("stays silent when the api cannot be read: an error is reported, not swallowed", () => {
    vi.mocked(useDataProvider).mockReturnValue({
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
    } as unknown as ReturnType<typeof useDataProvider>);
    vi.mocked(useGetList).mockImplementation(
      () =>
        ({
          data: undefined,
          total: 0,
          isPending: false,
          error: new Error("Service Unavailable"),
          refetch: vi.fn(),
        }) as unknown as ReturnType<typeof useGetList>,
    );
    const { result } = renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: 42 }),
    );
    expect(result.current.active).toEqual([]);
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it("asks both windows again when the bus says an incident moved", () => {
    windows([], []);
    state.subscribe.mockClear();
    state.refetch.active.mockClear();
    state.refetch.resolved.mockClear();
    renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: 42 }),
    );
    expect(state.subscribe).toHaveBeenCalledWith(
      "resource/OperationalIncident",
      expect.any(Function),
    );
    // the bus says that something moved, it never carries the state: both
    // windows go back to the api, which is what the stable refetch of each
    // window is named for (#1466)
    const [, refresh] = state.subscribe.mock.calls[0] as [string, () => void];
    refresh();
    expect(state.refetch.active).toHaveBeenCalledTimes(1);
    expect(state.refetch.resolved).toHaveBeenCalledTimes(1);
  });
});
