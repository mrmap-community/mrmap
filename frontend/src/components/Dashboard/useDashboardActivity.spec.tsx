import { CoreAdminContext, ListBase, testDataProvider, useListContext } from "react-admin";

import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { dashboardToday, type DashboardPeriod } from "./dashboardStatistics";
import { useDashboardActivity } from "./useDashboardActivity";
import { useDashboardStatistics } from "./useDashboardStatistics";

vi.mock("../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ api: { getOperation: () => ({}) }, isPending: false }),
}));

const Activity = ({ resources, period }: { resources: string[]; period: DashboardPeriod }) => {
  const sources = useDashboardActivity(resources, period);
  return <div data-testid="activity">{sources.map(source => `${source.resource}: ${source.statistics.status}`).join(", ")}</div>;
};
const Kpi = () => {
  const count = useListContext();
  const statistics = useDashboardStatistics("CatalogueService", count);
  return <div data-testid="kpi">{statistics.status}</div>;
};

const provider = () => ({
  getList: vi.fn().mockImplementation(async (resource: string) => resource.startsWith("Statistical")
    ? { data: [{ id: dashboardToday(), day: dashboardToday(), new: 3, updated: 2, deleted: 1 }], total: 1 }
    : { data: [{ id: "catalogue" }], total: 10 }),
});

describe("dashboard activity queries", () => {
  it("shares count and statistics requests with ResourceListCard and reuses them across filters", async () => {
    const dataProvider = provider();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const View = ({ period }: { period: DashboardPeriod }) => <CoreAdminContext dataProvider={testDataProvider(dataProvider)} queryClient={queryClient}>
      <ListBase resource="CatalogueService" perPage={1} queryOptions={{ meta: { jsonApiParams: { "fields[CatalogueService]": "id" } } }} disableSyncWithLocation>
        <Kpi />
      </ListBase>
      <Activity resources={["CatalogueService"]} period={period} />
    </CoreAdminContext>;
    const { rerender } = render(<View period={30} />);
    await waitFor(() => expect(screen.getByTestId("activity")).toHaveTextContent("CatalogueService: ready"));
    expect(screen.getByTestId("kpi")).toHaveTextContent("ready");
    expect(dataProvider.getList).toHaveBeenCalledTimes(2);
    expect(dataProvider.getList.mock.calls.map(call => call[0]).sort()).toEqual(["CatalogueService", "StatisticalCatalogueService"]);
    rerender(<View period={90} />);
    await waitFor(() => expect(screen.getByTestId("activity")).toHaveTextContent("ready"));
    expect(dataProvider.getList).toHaveBeenCalledTimes(2);
    queryClient.clear();
  });

  it("never queries unauthorized or unsupported resources", async () => {
    const dataProvider = provider();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(<CoreAdminContext dataProvider={testDataProvider(dataProvider)} queryClient={queryClient}>
      <Activity resources={["WebMapService", "User"]} period={30} />
    </CoreAdminContext>);
    expect(screen.getByTestId("activity")).toBeEmptyDOMElement();
    expect(dataProvider.getList).not.toHaveBeenCalled();
    rerender(<CoreAdminContext dataProvider={testDataProvider(dataProvider)} queryClient={queryClient}>
      <Activity resources={["DatasetMetadataRecord"]} period={7} />
    </CoreAdminContext>);
    await waitFor(() => expect(screen.getByTestId("activity")).toHaveTextContent("DatasetMetadataRecord: ready"));
    expect(dataProvider.getList.mock.calls.map(call => call[0]).sort()).toEqual(["DatasetMetadataRecord", "StatisticalDatasetMetadataRecord"]);
    queryClient.clear();
  });
});
