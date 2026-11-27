import { useGetList } from "react-admin";

import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import useServiceAlerts from "../Resource/ServiceAlert/useServiceAlerts";
import { useDashboardNotices } from "./useDashboardNotices";

const { getOperation } = vi.hoisted(() => ({ getOperation: vi.fn() }));

vi.mock("react-admin", () => ({ useGetList: vi.fn() }));
vi.mock("../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ api: { getOperation: getOperation } }),
}));
vi.mock("../Resource/ServiceAlert/useServiceAlerts", () => ({ default: vi.fn() }));

const NOW = Date.parse("2026-11-26T12:00:00Z");
const ALL = ["CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord"];

const answeredAlerts = (overrides: Record<string, unknown> = {}) => {
  vi.mocked(useServiceAlerts).mockReturnValue({
    data: [{
      id: "a1",
      severity: "error",
      category: "harvest_aborted",
      message: "harvest_aborted",
      serviceTitle: "Catalogue of things",
      occurredAt: "2026-11-26T09:00:00Z",
      targetPath: "/CatalogueService/c1/show",
    }],
    total: 1,
    error: undefined,
    isPending: false,
    ...overrides,
  } as unknown as ReturnType<typeof useServiceAlerts>);
};

const answeredTrail = (overrides: Record<string, unknown> = {}) => {
  vi.mocked(useGetList).mockReturnValue({
    data: [{
      id: "h1",
      historyType: "updated",
      historyDate: "2026-11-26T08:00:00Z",
      title: "Weather service",
      delta: [{ field: "title", old: "old", new: "new" }],
    }],
    total: 1,
    error: undefined,
    isPending: false,
    ...overrides,
  } as unknown as ReturnType<typeof useGetList>);
};

const auditResources = () =>
  vi.mocked(useGetList).mock.calls.map((call) => call[0]);

beforeEach(() => {
  vi.mocked(useServiceAlerts).mockReset();
  vi.mocked(useGetList).mockReset();
  getOperation.mockReturnValue({});
  answeredAlerts();
  answeredTrail();
});

describe("useDashboardNotices", () => {
  it("asks the alerts and the bounded page of every permitted changelog", () => {
    const { result } = renderHook(() => useDashboardNotices(ALL, NOW));
    expect(auditResources()).toEqual([
      "HistoricalCatalogueService",
      "HistoricalDatasetMetadataRecord",
      "HistoricalServiceMetadataRecord",
    ]);
    expect(vi.mocked(useGetList)).toHaveBeenCalledWith(
      "HistoricalCatalogueService",
      {
        pagination: { page: 1, perPage: 3 },
        sort: { field: "historyDate", order: "DESC" },
        // the dotted lookup of the changelog endpoint (#1080)
        filter: { historyDate_filter_lookup_gte: "2026-11-20T00:00:00Z" },
      },
      { enabled: true, retry: false },
    );
    expect(result.current.map((source) => `${source.resource}:${source.status}`)).toEqual([
      "ServiceAlert:ready",
      "CatalogueService:ready",
      "DatasetMetadataRecord:ready",
      "ServiceMetadataRecord:ready",
    ]);
  });

  it("maps the records of a source to rows which carry only what the api answered", () => {
    const { result } = renderHook(() => useDashboardNotices(ALL, NOW));
    expect(result.current[0].rows).toEqual([{
      id: "a1",
      source: "ServiceAlert",
      origin: "alert",
      kind: "error",
      occurredAt: "2026-11-26T09:00:00Z",
      target: "Catalogue of things",
      link: { pathname: "/CatalogueService/c1/show" },
      category: "harvest_aborted",
      message: "harvest_aborted",
    }]);
    expect(result.current[1].rows).toEqual([{
      id: "h1",
      source: "CatalogueService",
      origin: "audit",
      kind: "updated",
      occurredAt: "2026-11-26T08:00:00Z",
      target: "Weather service",
      link: { pathname: "/CatalogueService/h1/show" },
      delta: [{ field: "title" }],
    }]);
  });

  it("never asks a changelog the caller may not read or the schema does not answer", () => {
    const { result } = renderHook(() =>
      useDashboardNotices(["CatalogueService", "DatasetMetadataRecord"], NOW),
    );
    // the hook holds one read per audited resource and asks only the permitted
    // ones: the third read exists but is disabled and never reaches the api
    expect(auditResources()).toEqual([
      "HistoricalCatalogueService",
      "HistoricalDatasetMetadataRecord",
      "HistoricalServiceMetadataRecord",
    ]);
    expect(vi.mocked(useGetList).mock.calls.map((call) => call[2]?.enabled)).toEqual([
      true, true, false,
    ]);
    expect(result.current.map((source) => source.resource)).toEqual([
      "ServiceAlert", "CatalogueService", "DatasetMetadataRecord",
    ]);
    getOperation.mockReturnValue(undefined);
    const asked = vi.mocked(useGetList).mock.calls.length;
    const { result: unsupported } = renderHook(() => useDashboardNotices(ALL, NOW));
    expect(unsupported.current[1].status).toBe("unsupported");
    // the reads of the schema which does not answer the trail are disabled, so
    // the api is asked nothing about a changelog it cannot be asked about
    expect(vi.mocked(useGetList).mock.calls.slice(asked).map((call) => call[2]?.enabled)).toEqual([
      false, false, false,
    ]);
  });

  it("keeps a refused read apart from a failed one and from an empty one", () => {
    answeredTrail({ data: [], total: 0 });
    const empty = renderHook(() => useDashboardNotices(ALL, NOW));
    expect(empty.result.current[1].status).toBe("ready");
    expect(empty.result.current[1].rows).toEqual([]);
    expect(empty.result.current[1].total).toBe(0);

    answeredTrail({ error: { status: 403 } });
    const refused = renderHook(() => useDashboardNotices(ALL, NOW));
    expect(refused.result.current[1].status).toBe("forbidden");
    expect(refused.result.current[1].rows).toEqual([]);

    answeredTrail({ error: { status: 500 } });
    const failed = renderHook(() => useDashboardNotices(ALL, NOW));
    expect(failed.result.current[1].status).toBe("error");

    answeredTrail({ isPending: true });
    const loading = renderHook(() => useDashboardNotices(ALL, NOW));
    expect(loading.result.current[1].status).toBe("loading");
  });

  it("answers the alerts source by the state of the shared alerts read", () => {
    answeredAlerts({ isPending: true });
    const loading = renderHook(() => useDashboardNotices(ALL, NOW));
    expect(loading.result.current[0].status).toBe("loading");
    answeredAlerts({ error: { status: 401 } });
    const refused = renderHook(() => useDashboardNotices(ALL, NOW));
    expect(refused.result.current[0].status).toBe("forbidden");
  });

  it("never asks a changelog beyond the bounded window it says it answers", () => {
    renderHook(() => useDashboardNotices(ALL, NOW));
    const [, params] = vi.mocked(useGetList).mock.calls[0] ?? [];
    expect(params?.pagination).toEqual({ page: 1, perPage: 3 });
    expect(Object.values(params?.filter ?? {})).toEqual(["2026-11-20T00:00:00Z"]);
  });
});
