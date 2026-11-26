import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useDashboardStatistics } from "./useDashboardStatistics";

const { getList, getOperation } = vi.hoisted(() => ({ getList: vi.fn(), getOperation: vi.fn() }));
vi.mock("react-admin", () => ({ useGetList: getList }));
vi.mock("../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ api: { getOperation } }),
}));

const count = { total: 0, isPending: false };

beforeEach(() => {
  getOperation.mockReturnValue({});
  getList.mockReturnValue({ data: [], total: 0 });
});

describe("useDashboardStatistics", () => {
  it("shares one bounded request across all selected periods", () => {
    const hook = renderHook(({ period }: { period: 7 | 30 | 90 }) =>
      useDashboardStatistics("CatalogueService", count, period), { initialProps: { period: 7 as 7 | 30 | 90 } });
    const args = getList.mock.lastCall;
    expect(args).toMatchObject(["StatisticalCatalogueService", {
      pagination: { page: 1, perPage: 90 }, sort: { field: "id", order: "DESC" },
    }, { enabled: true }]);
    hook.rerender({ period: 90 });
    expect(getList.mock.lastCall).toEqual(args);
    expect(hook.result.current.status).toBe("ready");
  });

  it("disables a global aggregate for filtered inventory and missing operations", () => {
    const filtered = renderHook(() => useDashboardStatistics("CatalogueService", {
      ...count, filterValues: { title: "private" },
    }));
    expect(filtered.result.current.status).toBe("unsupported");
    expect(getList.mock.lastCall?.[2].enabled).toBe(false);
    getOperation.mockReturnValue(undefined);
    const missing = renderHook(() => useDashboardStatistics("CatalogueService", count));
    expect(missing.result.current.status).toBe("unsupported");
    expect(getList.mock.lastCall?.[2].enabled).toBe(false);
  });

  it("keeps pending, failed and incomplete responses distinct", () => {
    const hook = renderHook(() => useDashboardStatistics("DatasetMetadataRecord", count));
    for (const [answer, expected] of [
      [{ isPending: true }, "loading"], [{ error: Error("unavailable") }, "error"],
      [{ data: [], total: 2 }, "partial"],
    ] as const) {
      getList.mockReturnValue(answer);
      hook.rerender();
      expect(hook.result.current.status).toBe(expected);
    }
  });
});
