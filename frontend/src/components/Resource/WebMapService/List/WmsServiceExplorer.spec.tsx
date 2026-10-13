import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import {
  AdminContext,
  type ListControllerResult,
  ListContextProvider,
  ResourceContextProvider,
  testDataProvider,
} from "react-admin";
import { beforeEach, describe, expect, it, vi } from "vitest";
import WmsServiceExplorer from "./WmsServiceExplorer";

// the button which opens a service in the map viewer asks the capabilities of
// that service and needs the ows context of the whole application
vi.mock("../Button/ListActions", () => ({ default: () => null }));

const services = [
  {
    id: "0b1f-1",
    title: "Soil layers",
    abstract: "The layers of soil of the region",
    hits: 12,
    isSecured: true,
    monitoringFailed: true,
    monitoringFailedAt: "2026-10-01T10:00:00Z",
    lastModifiedAt: "2026-10-02T10:00:00Z",
  },
  { id: "0b1f-2", title: "Cadastral maps", abstract: "The cadastre", hits: 3 },
];

const getList = vi.fn();
const setFilters = vi.fn();
// the realtime subscription of RealtimeListBase is answered by the proxy of
// react-admin, which requires the answer of the dataProvider to be a promise
const subscribe = vi.fn().mockResolvedValue(undefined);
const unsubscribe = vi.fn().mockResolvedValue(undefined);
const dataProvider = testDataProvider({
  getList,
  subscribe,
  unsubscribe,
});

/** the list controller the screen of the services reads its services from */
const renderExplorer = (
  filter: Record<string, unknown> = {},
  records: unknown[] = services,
) => {
  const context = {
    data: records,
    total: records.length,
    isPending: false,
    isFetching: false,
    isEmpty: false,
    error: null,
    resource: "WebMapService",
    filter,
    filterValues: filter,
    setFilters,
    sort: { field: "title", order: "ASC" },
    setSort: vi.fn(),
    setPage: vi.fn(),
    page: 1,
    perPage: 25,
    refetch: vi.fn(),
  } as unknown as ListControllerResult;

  return render(
    <AdminContext dataProvider={dataProvider}>
      <ResourceContextProvider value="WebMapService">
        <ListContextProvider value={context}>
          <WmsServiceExplorer />
        </ListContextProvider>
      </ResourceContextProvider>
    </AdminContext>,
  );
};

beforeEach(() => {
  getList.mockReset();
  getList.mockResolvedValue({ data: [], total: 0 });
  setFilters.mockReset();
});

describe("WmsServiceExplorer", () => {
  it("answers one compact row per service of the list", async () => {
    renderExplorer();
    expect(await screen.findByText("Soil layers")).toBeInTheDocument();
    expect(screen.getByText("Cadastral maps")).toBeInTheDocument();
    expect(screen.getByText("0b1f-1")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    // the layers of a service are counted by the layers which belong to it, asked
    // as one record of them and only their id
    expect(getList).toHaveBeenCalledWith(
      "Layer",
      expect.objectContaining({
        pagination: { page: 1, perPage: 1 },
        meta: expect.objectContaining({
          relatedResource: { resource: "WebMapService", id: "0b1f-1" },
          jsonApiParams: { "fields[Layer]": "id" },
        }),
      }),
    );
  });

  it("marks the states of attention and of security in the row", async () => {
    renderExplorer();
    const row = await screen.findByText("Soil layers");
    expect(
      within(row.closest("tr") as HTMLElement).getByText(
        "serviceAttention.shortLabels.monitoringFailed",
      ),
    ).toBeInTheDocument();
    expect(
      within(row.closest("tr") as HTMLElement).getByText("serviceList.secured"),
    ).toBeInTheDocument();
    // the service without any state is the only one which needs no attention
    expect(
      screen.getAllByText("serviceAttention.shortLabels.healthy"),
    ).toHaveLength(1);
  });

  it("answers a message when no service is left of the filters", async () => {
    renderExplorer({ search: "nothing" }, []);
    expect(await screen.findByText("serviceList.empty")).toBeInTheDocument();
  });

  it("narrows the list to the chosen facet and keeps the search", async () => {
    renderExplorer({ search: "soil", is_update_candidate: false });
    fireEvent.click(
      await screen.findByRole("button", {
        name: "serviceList.facets.updateFailed",
      }),
    );
    expect(setFilters).toHaveBeenCalledWith({
      search: "soil",
      updateFailed: true,
    });
  });

  it("shows the tiles as counts of the services of the current filters", async () => {
    renderExplorer({ search: "soil" });
    expect(
      await screen.findByText("serviceList.tiles.total"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("serviceList.tiles.runningUpdates"),
    ).toBeInTheDocument();
    await screen.findByText("serviceList.tiles.needsAttention");
    // the services are counted with the search of the list and the state of the tile
    expect(getList).toHaveBeenCalledWith(
      "WebMapService",
      expect.objectContaining({
        filter: expect.objectContaining({ search: "soil", hasAlert: true }),
      }),
    );
  });

  it("shows the details and the updates of the service which is selected", async () => {
    renderExplorer();
    fireEvent.click(await screen.findByText("Soil layers"));
    expect(
      await screen.findByText("serviceList.recentEvents"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("0b1f-1").length).toBeGreaterThan(1);
    expect(
      await screen.findByText("serviceList.noRecentEvents"),
    ).toBeInTheDocument();
    expect(getList).toHaveBeenCalledWith(
      "WebMapServiceUpdateJob",
      expect.objectContaining({
        filter: { service: "0b1f-1" },
        sort: { field: "dateCreated", order: "DESC" },
        pagination: { page: 1, perPage: 5 },
      }),
    );
  });
});
