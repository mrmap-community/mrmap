import type { DashboardPeriod } from "./dashboardStatistics";

import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDashboardCounts, useDashboardInventory } from "./useDashboardInventory";

const { getList, getOperation } = vi.hoisted(() => ({ getList: vi.fn(), getOperation: vi.fn() }));
vi.mock("react-admin", () => ({ useGetList: getList }));
vi.mock("../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ api: { getOperation } }),
}));

const kinds = [
  "WebMapService", "Layer", "WebFeatureService", "FeatureType",
  "CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord",
];
const PERIOD = 30 satisfies DashboardPeriod;

/** the resources whose query actually asks the api - a kind the caller may not
 *  read is mounted with a disabled query, which never reaches the api (#1814) */
const asked = () => getList.mock.calls.filter(call => call[2]?.enabled !== false);
const askedOf = (statistics: boolean) => asked().map(call => call[0] as string)
  .filter(resource => resource.startsWith("Statistical") === statistics);
const askedResources = () => askedOf(false);
const askedStatistics = () => askedOf(true);

beforeEach(() => {
  getList.mockReset();
  getOperation.mockReturnValue({});
  getList.mockReturnValue({ data: [], total: 0, isPending: false });
});

describe("useDashboardInventory", () => {
  it("reads the stock of every authorized kind, asking the count of it once", () => {
    renderHook(() => useDashboardInventory(kinds, PERIOD));
    // one count-only read and one bounded statistics read per kind - the three
    // complementary charts of #1820 mount this hook once for the whole screen,
    // so nothing on it reads the same resource twice (#1814)
    // the count-only read of every authorized kind ...
    expect(askedResources()).toEqual(kinds);
    // ... plus the daily statistics of exactly the three kinds the api of #1817
    // answers them for: the four others are reported as unprovable by the
    // charts instead of being asked a resource which does not exist
    expect(askedStatistics()).toEqual([
      "StatisticalCatalogueService", "StatisticalDatasetMetadataRecord",
      "StatisticalServiceMetadataRecord",
    ]);
    expect(getList).toHaveBeenCalledWith("Layer", expect.objectContaining({
      pagination: { page: 1, perPage: 1 },
      sort: { field: "id", order: "ASC" },
      filter: {},
      // the very query of the KPI card of #1817, which is what lets react-query
      // answer both cards from one request
      meta: { jsonApiParams: { "fields[Layer]": "id" } },
    }), expect.objectContaining({ enabled: true }));
  });

  it("asks nothing of a kind the caller may not read", () => {
    renderHook(() => useDashboardInventory(["Layer", "CatalogueService"], PERIOD));
    expect(askedResources()).toEqual(["Layer", "CatalogueService"]);
    expect(askedStatistics()).toEqual(["StatisticalCatalogueService"]);
  });

  it("answers the verified stock and the count of today of each kind", () => {
    const { result } = renderHook(() => useDashboardInventory(["CatalogueService"], PERIOD));
    expect(result.current).toEqual([{
      resource: "CatalogueService",
      status: "ready",
      days: expect.any(Array),
      count: 0,
    }]);
  });

  it("keeps a loading, failed and partial read apart from a stock of zero", () => {
    for (const [answer, expected] of [
      [{ isPending: true }, "loading"],
      [{ error: Error("unavailable"), isPending: false }, "error"],
      [{ data: [], total: 2, isPending: false }, "partial"],
    ] as const) {
      getList.mockImplementation((_resource: string, params: { pagination?: { perPage?: number } }) =>
        params.pagination?.perPage === 1 ? { ...answer, days: undefined } : answer);
      const hook = renderHook(() => useDashboardInventory(["CatalogueService"], PERIOD));
      expect(hook.result.current[0].status).toBe(expected);
    }
  });
});

describe("useDashboardCounts", () => {
  it("reads the count of every authorized kind and nothing else", () => {
    // the donut answers an inventory and not a history, so a kind without any
    // verified statistics (#1817) still counts today - and the read is the one
    // of the KPI tile, which is why the card costs the screen no request
    renderHook(() => useDashboardCounts(["Layer", "FeatureType"]));
    expect(askedResources()).toEqual(["Layer", "FeatureType"]);
  });

  it("answers the answered counts and names the missing ones", () => {
    getList.mockImplementation((resource: string) =>
      resource === "Layer"
        ? { data: [], total: 41, isPending: false }
        : { data: [], isPending: true });
    const { result } = renderHook(() => useDashboardCounts(["Layer", "FeatureType"]));
    expect(result.current).toEqual([
      { resource: "Layer", status: "ready", count: 41 },
      { resource: "FeatureType", status: "loading" },
    ]);
  });

  it("asks nothing of a kind the caller may not read", () => {
    const { result } = renderHook(() => useDashboardCounts([]));
    expect(askedResources()).toEqual([]);
    expect(result.current).toEqual([]);
  });
});

