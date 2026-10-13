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
import { SUMMARY_TILES } from "./ServiceSummaryTiles";
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
    // the api annotates the page of services with the count of the layers
    elementCount: 3,
  },
  {
    id: "0b1f-2",
    title: "Cadastral maps",
    abstract: "The cadastre",
    hits: 3,
    // a service which answers its layers but not the annotation is counted by them
    layers: ["1a", "1b"],
  },
];

const getList = vi.fn();
const setFilters = vi.fn();
const setSort = vi.fn();
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
    // the filter of the query carries the filter the list applies on its own,
    // the filters which are stored are the ones a facet narrows
    filter: { is_update_candidate: false, ...filter },
    filterValues: filter,
    displayedFilters: {},
    setFilters,
    sort: { field: "title", order: "ASC" },
    setSort,
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
  setSort.mockReset();
});

describe("WmsServiceExplorer", () => {
  it("answers one compact row per service of the list", async () => {
    renderExplorer();
    expect(await screen.findByText("Soil layers")).toBeInTheDocument();
    expect(screen.getByText("Cadastral maps")).toBeInTheDocument();
    expect(screen.getByText("0b1f-1")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
    // the layers of a service are counted by the service itself: by the annota-
    // tion of the page and, where that is missing, by the layers of the service
    const rows = screen.getAllByRole("row");
    expect(within(rows[1] as HTMLElement).getByText("3")).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).getByText("2")).toBeInTheDocument();
    // and so nothing is asked for a row of itself
    expect(getList.mock.calls.filter((call) => call[0] === "Layer")).toEqual(
      [],
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
    renderExplorer({ search: "soil" });
    fireEvent.click(
      await screen.findByRole("button", {
        name: "serviceList.facets.updateFailed",
      }),
    );
    // the facet is named as the api filters it, which is the source of the filter
    // the filter button of the list offers for the same state - and the filter
    // the list applies on its own is not carried by the facet
    expect(setFilters).toHaveBeenCalledWith(
      { search: "soil", update_failed: true },
      {},
    );
  });

  it("lights the facet which a filter of the filter button answers", async () => {
    // the search narrows, a filter of the list narrows and the facet of that
    // state is the one which is chosen - one state, asked in one way
    renderExplorer({ has_alert: true });
    expect(
      await screen.findByRole("button", {
        name: "serviceList.facets.needsAttention",
      }),
    ).toHaveClass("Mui-selected");
    expect(
      screen.getByRole("button", { name: "serviceList.facets.all" }),
    ).not.toHaveClass("Mui-selected");
  });

  it("orders the list by a column which the api orders by", async () => {
    renderExplorer();
    await screen.findByText("Soil layers");
    // the columns of the layers and of the last change do not order the list,
    // because the api refuses a sort by them
    expect(document.querySelectorAll(".MuiTableSortLabel-root")).toHaveLength(
      3,
    );
    fireEvent.click(screen.getByText("serviceList.columns.hits"));
    expect(setSort).toHaveBeenCalledWith({ field: "hits", order: "ASC" });
    // the column the list is ordered by shows the direction it is ordered by,
    // which is the column of the title the list starts at
    const orderedBy = document.querySelector(
      ".MuiTableSortLabel-root.Mui-active",
    );
    expect(orderedBy?.textContent).toEqual("serviceList.columns.service");
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
    // the services are counted with the search of the list and the state of the
    // tile, both named as the api filters them
    expect(getList).toHaveBeenCalledWith(
      "WebMapService",
      expect.objectContaining({
        filter: expect.objectContaining({ search: "soil", has_alert: true }),
      }),
    );
    expect(getList).toHaveBeenCalledWith(
      "BackgroundProcess",
      expect.objectContaining({
        filter: expect.objectContaining({
          search: "soil",
          status: "pending,running",
          process_type: "update",
        }),
      }),
    );
    // every tile is marked by the icon of its state
    expect(
      document.querySelectorAll(".MuiSvgIcon-root").length,
    ).toBeGreaterThanOrEqual(SUMMARY_TILES.length);
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
