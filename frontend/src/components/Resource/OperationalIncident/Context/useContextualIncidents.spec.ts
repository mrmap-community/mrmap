import { useDataProvider, useGetList } from "react-admin";

import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type OperationalIncidentRecord } from "../incidentContract";
import useContextualIncidents, {
  parseTargetKey,
} from "./useContextualIncidents";

vi.mock("react-admin", () => ({
  useDataProvider: vi.fn(),
  useGetList: vi.fn(),
}));

const incident = (
  overrides: Partial<OperationalIncidentRecord> & { id: string | number },
): OperationalIncidentRecord => ({
  code: "harvest.chord_stalled",
  sourceType: "harvesting",
  severity: "warning",
  state: "retrying",
  summary: "the endpoint did not answer",
  occurrenceCount: 1,
  firstOccurrence: "2026-11-14T10:00:00Z",
  lastOccurrence: "2026-11-14T10:00:00Z",
  targetPath: "/HarvestingJob/42/show",
  ...overrides,
});

/** the two windows the hook reads, keyed by the `state` facet it filters on */
const windows = (
  active: OperationalIncidentRecord[],
  resolved: OperationalIncidentRecord[],
) => {
  vi.mocked(useDataProvider).mockReturnValue({
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
  } as unknown as ReturnType<typeof useDataProvider>);
  vi.mocked(useGetList).mockImplementation((_resource, params) => {
    const filter = (
      params as unknown as { filter: { state: string } }
    ).filter;
    const rows = filter.state === "resolved" ? resolved : active;
    return {
      data: rows,
      total: rows.length,
      isPending: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useGetList>;
  });
};

describe("parseTargetKey", () => {
  it("reads the resource and id a show path names", () => {
    expect(parseTargetKey("/HarvestingJob/42/show")).toEqual({
      resource: "HarvestingJob",
      id: "42",
    });
    expect(parseTargetKey("/CatalogueService/5/show/records")).toEqual({
      resource: "CatalogueService",
      id: "5",
    });
    expect(parseTargetKey("/WebMapService/9/show?tab=alerts")).toEqual({
      resource: "WebMapService",
      id: "9",
    });
  });

  it("names nothing for a path without a show segment or no path at all", () => {
    expect(parseTargetKey("/HarvestingJob/42/edit")).toBeNull();
    expect(parseTargetKey(undefined)).toBeNull();
    expect(parseTargetKey(null)).toBeNull();
  });
});

describe("useContextualIncidents", () => {
  it("keeps only the incidents about the record of the screen", () => {
    windows(
      [
        incident({ id: "a", targetPath: "/HarvestingJob/42/show" }),
        incident({ id: "b", targetPath: "/HarvestingJob/7/show" }),
        incident({ id: "c", targetPath: "/WebMapService/42/show" }),
      ],
      [],
    );
    const { result } = renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: 42 }),
    );
    expect(result.current.active.map((r) => r.id)).toEqual(["a"]);
  });

  it("never surfaces an incident whose target path was withheld", () => {
    windows(
      [
        incident({ id: "secret", targetPath: null }),
        incident({ id: "mine", targetPath: "/HarvestingJob/42/show" }),
      ],
      [],
    );
    const { result } = renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: "42" }),
    );
    expect(result.current.active.map((r) => r.id)).toEqual(["mine"]);
  });

  it("draws one entry per incident though the window repeats it", () => {
    windows(
      [
        incident({ id: "dup", targetPath: "/HarvestingJob/42/show" }),
        incident({ id: "dup", targetPath: "/HarvestingJob/42/show" }),
      ],
      [],
    );
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
          lastOccurrence: "2026-11-14T12:00:00Z",
        }),
        incident({
          id: "err-old",
          severity: "error",
          lastOccurrence: "2026-11-14T09:00:00Z",
        }),
        incident({
          id: "warn-old",
          severity: "warning",
          lastOccurrence: "2026-11-14T08:00:00Z",
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
      [incident({ id: "active", targetPath: "/HarvestingJob/42/show" })],
      [
        incident({
          id: "resolved",
          state: "resolved",
          resolvedAt: "2026-11-13T10:00:00Z",
          targetPath: "/HarvestingJob/42/show",
        }),
        incident({
          id: "resolved-other",
          state: "resolved",
          targetPath: "/HarvestingJob/99/show",
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
      expect(Object.keys(filter)).toEqual(["state"]);
      expect(filter.state).not.toMatch(/[Tt]arget/);
    }
  });

  it("stays silent while the api is not there: an error is reported, not swallowed", () => {
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
          error: new Error("unknown resource"),
          refetch: vi.fn(),
        }) as unknown as ReturnType<typeof useGetList>,
    );
    const { result } = renderHook(() =>
      useContextualIncidents({ resource: "HarvestingJob", id: 42 }),
    );
    expect(result.current.active).toEqual([]);
    expect(result.current.error).toBeInstanceOf(Error);
  });
});
