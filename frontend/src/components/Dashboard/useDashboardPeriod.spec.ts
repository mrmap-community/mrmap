import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DASHBOARD_PERIODS, DEFAULT_DASHBOARD_PERIOD, useDashboardPeriod } from "./useDashboardPeriod";

const invalidate = vi.hoisted(() => vi.fn());
const queryClient = { invalidateQueries: invalidate };
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => queryClient }));

beforeEach(() => {
  invalidate.mockClear();
});

const askedKeys = () =>
  (invalidate.mock.lastCall?.[0]?.predicate ?? (() => true)) as (query: { queryKey: unknown[] }) => boolean;

describe("useDashboardPeriod", () => {
  it("answers the window of the mockup as the default of the whole screen", () => {
    const { result } = renderHook(() => useDashboardPeriod());
    expect(result.current.period).toBe(DEFAULT_DASHBOARD_PERIOD);
    expect(DASHBOARD_PERIODS).toEqual([7, 30, 90]);
  });

  it("changes the window of every card at once", () => {
    const { result } = renderHook(() => useDashboardPeriod());
    act(() => result.current.setPeriod(90));
    expect(result.current.period).toBe(90);
    // the window is a key of the statistics reads, so no refresh is asked for a
    // new period: the cards ask exactly the window their period names
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("refreshes the reads of the screen and nothing else", () => {
    const { result } = renderHook(() => useDashboardPeriod());
    act(() => result.current.refresh());
    const answers = (resource: string) => askedKeys()({ queryKey: [resource] });
    // the counts, the daily statistics, the audit trails, the alerts of the
    // notices, the queues and the state of the deployment answer again ...
    for (const resource of [
      "Layer", "StatisticalCatalogueService", "HistoricalDatasetMetadataRecord",
      "ServiceAlert", "BackgroundProcess", "SystemStatus",
    ]) expect(answers(resource)).toBe(true);
    // ... while the schema, the permissions and the lists an administrator
    // happened to open are left alone
    for (const resource of ["openapi", "getCapabilities", "CatalogueService_list"]) {
      expect(answers(resource)).toBe(false);
    }
  });

  it("names the moment of the last refresh of the whole screen", () => {
    const { result } = renderHook(() => useDashboardPeriod());
    expect(result.current.refreshedAt).toBeNull();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-26T12:00:00Z"));
    act(() => result.current.refresh());
    expect(result.current.refreshedAt).toBe(Date.parse("2026-11-26T12:00:00Z"));
    vi.useRealTimers();
  });

  it("keeps the window while the screen is refreshed", () => {
    const { result } = renderHook(() => useDashboardPeriod());
    act(() => result.current.setPeriod(7));
    act(() => result.current.refresh());
    expect(result.current.period).toBe(7);
  });
});

