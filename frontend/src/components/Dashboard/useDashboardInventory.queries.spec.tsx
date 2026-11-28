import { CoreAdminContext, ListBase, testDataProvider, useListContext } from "react-admin";

import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { dashboardToday } from "./dashboardStatistics";
import { useDashboardCounts, useDashboardInventory } from "./useDashboardInventory";

vi.mock("../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ api: { getOperation: () => ({}) }, isPending: false }),
}));

const PERIOD = 30 as const;

/**
 * The three complementary charts of #1820 read the inventory together with the
 * KPI tiles of #1817, so the screen must not pay one request per card. The
 * charts ask the very query of the tile — count-only, `id` fields only — which
 * is what lets react-query answer tile, line, bars and circle from one read.
 */
describe("the inventory reads of the screen", () => {
  const Chart = ({ resource }: { resource: string }) => {
    const sources = useDashboardInventory([resource], PERIOD);
    return <div data-testid="chart">{sources[0]?.status}</div>;
  };
  const Donut = ({ resource }: { resource: string }) => {
    const sources = useDashboardCounts([resource]);
    return <div data-testid="donut">{sources.map(source => source.status).join(",")}</div>;
  };
  const Tile = () => {
    const count = useListContext();
    return <div data-testid="tile">{count.total ?? "pending"}</div>;
  };

  const answer = (resource: string) =>
    resource.startsWith("Statistical")
      ? { data: [{ id: dashboardToday(), day: dashboardToday(), new: 3, updated: 2, deleted: 1 }], total: 1 }
      : { data: [{ id: "layer" }], total: 41 };

  it("asks each read once for the tile, the line and the circle", async () => {
    const dataProvider = { getList: vi.fn().mockImplementation(async (resource: string) => answer(resource)) };
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<CoreAdminContext dataProvider={testDataProvider(dataProvider)} queryClient={queryClient}>
      <ListBase resource="CatalogueService" perPage={1} queryOptions={{ meta: { jsonApiParams: { "fields[CatalogueService]": "id" } } }} disableSyncWithLocation>
        <Tile />
      </ListBase>
      <Chart resource="CatalogueService" />
      <Donut resource="CatalogueService" />
      <Donut resource="Layer" />
    </CoreAdminContext>);
    await waitFor(() => expect(screen.getByTestId("chart")).toHaveTextContent("ready"));
    await waitFor(() => expect(screen.getAllByTestId("donut")[0]).toHaveTextContent("ready"));
    expect(screen.getByTestId("tile")).toHaveTextContent("41");
    const asked = dataProvider.getList.mock.calls.map(call => call[0]).sort();
    // the tile of the KPI row, the line of the inventory chart and the arc of
    // the donut answer one read of the count of CatalogueService, and nothing on
    // the screen asks the api the same thing twice (#1814)
    expect(asked).toEqual(["CatalogueService", "Layer", "StatisticalCatalogueService"]);
  });
});
