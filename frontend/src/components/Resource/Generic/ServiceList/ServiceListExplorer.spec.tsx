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
import { CATALOGUE_SERVICE_LIST_CONFIG } from "../../CatalogueService/CatalogueServiceList";
import { WFS_SERVICE_LIST_CONFIG } from "../../WebFeatureService/List/ListWebFeatureService";
import { WMS_SERVICE_LIST_CONFIG } from "../../WebMapService/List/ListWebMapService";
import { type ServiceListConfig } from "./config";
import ServiceListExplorer from "./ServiceListExplorer";
import { summaryTiles } from "./ServiceSummaryTiles";

// the details card asks the schema of the api for the fields of its resource
// and shows the preview of the service, which both belong to the integration
// of the application and are answered by a marker which names the protocol of
// the panel and the service it shows
vi.mock("../ServiceShow/ServiceDetailsCard", async () => {
  const react = await vi.importActual<typeof import("react")>("react");
  const reactAdmin =
    await vi.importActual<typeof import("react-admin")>("react-admin");
  const ServiceDetailsCardMock = ({ protocol }: { protocol: string }) => {
    const record = reactAdmin.useRecordContext();
    return react.createElement(
      "span",
      null,
      `details-${protocol}-${record?.id ?? "none"}`,
    );
  };
  return { default: ServiceDetailsCardMock };
});

/** the three kinds of service the screen of registered services answers */
const CONFIGS: { name: string; config: ServiceListConfig }[] = [
  { name: "WebMapService", config: WMS_SERVICE_LIST_CONFIG },
  { name: "WebFeatureService", config: WFS_SERVICE_LIST_CONFIG },
  { name: "CatalogueService", config: CATALOGUE_SERVICE_LIST_CONFIG },
];

/**
 * The services of the list. The first answers the count of its elements as the
 * annotation of the page and its elements as relationship beside it, so the
 * annotation wins; the second answers only the relationship, which is where the
 * screen falls back to - except for catalogues, which answer the annotation
 * alone.
 */
const recordsFor = (config: ServiceListConfig) => [
  {
    id: "0b1f-1",
    title: "Soil data",
    abstract: "The layers of soil of the region",
    hits: 12,
    // a secured service is marked only where the api answers security for it
    ...(config.resource === "WebMapService" ? { isSecured: true } : {}),
    monitoringFailed: true,
    monitoringFailedAt: "2026-10-01T10:00:00Z",
    lastModifiedAt: "2026-10-02T10:00:00Z",
    elementCount: 3,
    ...(config.countRelation ? { [config.countRelation]: ["a", "b"] } : {}),
  },
  {
    id: "0b1f-2",
    title: "Cadastral parcels",
    abstract: "The cadastre",
    hits: 4,
    lastModifiedAt: "2026-10-03T10:00:00Z",
    ...(config.countRelation ? { [config.countRelation]: ["x"] } : {}),
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
const listContext = (
  config: ServiceListConfig,
  filter: Record<string, unknown> = {},
  records: unknown[] = recordsFor(config),
  isPending = false,
): ListControllerResult => {
  // only the lists of web map services and of web feature services apply the
  // filter of the update candidates on their own - see jsonapi/components/
  // ListGuesser.tsx
  const own =
    config.resource === "CatalogueService"
      ? {}
      : { is_update_candidate: false };
  return {
    data: records,
    total: records.length,
    isPending,
    isFetching: false,
    isEmpty: false,
    error: null,
    resource: config.resource,
    // the filter of the query carries the filter the list applies on its own,
    // the filters which are stored are the ones a facet narrows
    filter: { ...own, ...filter },
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
};

const explorer = (context: ListControllerResult) => (
  <AdminContext dataProvider={dataProvider}>
    <ResourceContextProvider value={context.resource}>
      <ListContextProvider value={context}>
        <ServiceListExplorer
          config={
            CONFIGS.find((candidate) => candidate.name === context.resource)!
              .config
          }
        />
      </ListContextProvider>
    </ResourceContextProvider>
  </AdminContext>
);

/** the screen of one kind of service, narrowed by the given filters */
const renderExplorer = (
  config: ServiceListConfig,
  filter: Record<string, unknown> = {},
  records?: unknown[],
  isPending = false,
) => render(explorer(listContext(config, filter, records, isPending)));

beforeEach(() => {
  getList.mockReset();
  getList.mockResolvedValue({ data: [], total: 0 });
  setFilters.mockReset();
  setSort.mockReset();
});

describe.each(CONFIGS)("$name", ({ config }) => {
  it("answers one compact row per service of the list", async () => {
    renderExplorer(config);
    expect(await screen.findByText("Soil data")).toBeInTheDocument();
    expect(screen.getByText("Cadastral parcels")).toBeInTheDocument();
    expect(screen.getByText("0b1f-1")).toBeInTheDocument();
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(3);
    // the elements of a service are counted by the service itself: by the
    // annotation of the page and, where that is missing, by the relationship
    // of the service - except for catalogues, which answer the annotation alone
    expect(within(rows[1] as HTMLElement).getByText("3")).toBeInTheDocument();
    if (config.countRelation) {
      expect(within(rows[2] as HTMLElement).getByText("1")).toBeInTheDocument();
    }
    // and so nothing is asked for a row of itself
    expect(
      getList.mock.calls.filter(([resource]) =>
        [
          "Layer",
          "FeatureType",
          "DatasetMetadataRecord",
          "ServiceMetadataRecord",
          "HarvestingJob",
        ].includes(resource as string),
      ),
    ).toEqual([]);
  });

  it("labels the count column with the elements of its resource", async () => {
    renderExplorer(config);
    expect(
      await screen.findByText(`serviceList.columns.${config.countLabelKey}`),
    ).toBeInTheDocument();
  });

  it("marks the states of attention in the row", async () => {
    renderExplorer(config);
    const title = await screen.findByText("Soil data");
    const row = title.closest("tr") as HTMLElement;
    expect(
      within(row).getByText("serviceAttention.shortLabels.monitoringFailed"),
    ).toBeInTheDocument();
    // the service without any state is the only one which needs no attention
    expect(
      screen.getAllByText("serviceAttention.shortLabels.healthy"),
    ).toHaveLength(1);
    // the security of a service is marked only where the api answers it
    const secured = within(row).queryByText("serviceList.secured");
    if (config.resource === "WebMapService") {
      expect(secured).toBeInTheDocument();
    } else {
      expect(secured).toBeNull();
    }
  });

  it("narrows the list to the chosen facet and keeps the search", async () => {
    renderExplorer(config, { search: "soil" });
    fireEvent.click(
      await screen.findByRole("button", {
        name: "serviceList.facets.updateFailed",
      }),
    );
    // the facet is named as the api filters it, which is the source of the
    // filter the filter button of the list offers for the same state - and the
    // filter the list applies on its own is not carried by the facet
    expect(setFilters).toHaveBeenCalledWith(
      { search: "soil", update_failed: true },
      {},
    );
  });

  it("shows the details of the selected service with its protocol", async () => {
    renderExplorer(config);
    fireEvent.click(await screen.findByText("Soil data"));
    expect(
      await screen.findByText(`details-${config.protocol}-0b1f-1`),
    ).toBeInTheDocument();
    // the selected row is highlighted
    const selected = document.querySelectorAll("tr.Mui-selected");
    expect(selected).toHaveLength(1);
    expect(selected[0]?.textContent).toContain("Soil data");
  });

  it("does not select a row through its action buttons", async () => {
    renderExplorer(config);
    await screen.findByText("Soil data");
    const rows = screen.getAllByRole("row");
    const actions = within(rows[1] as HTMLElement).getAllByRole("link");
    expect(actions.length).toBeGreaterThan(0);
    fireEvent.click(actions[0] as HTMLElement);
    expect(document.querySelectorAll("tr.Mui-selected")).toHaveLength(0);
    expect(screen.queryByText(`details-${config.protocol}-0b1f-1`)).toBeNull();
  });

  it("clears the selection when the service leaves the results", async () => {
    const { rerender } = renderExplorer(config);
    fireEvent.click(await screen.findByText("Soil data"));
    expect(
      await screen.findByText(`details-${config.protocol}-0b1f-1`),
    ).toBeInTheDocument();
    // the search narrows the page until the selected service is gone
    rerender(
      explorer(
        listContext(config, { search: "parcel" }, recordsFor(config).slice(1)),
      ),
    );
    expect(screen.queryByText(`details-${config.protocol}-0b1f-1`)).toBeNull();
    expect(document.querySelectorAll("tr.Mui-selected")).toHaveLength(0);
  });

  it("counts the services of the current filters in the tiles", async () => {
    renderExplorer(config, { search: "soil" });
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
      config.resource,
      expect.objectContaining({
        filter: expect.objectContaining({ search: "soil", has_alert: true }),
      }),
    );
    // the running updates stay the processes of any service - no filter of the
    // resource of the list is introduced on them
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
    ).toBeGreaterThanOrEqual(summaryTiles(config.resource).length);
  });

  it("answers a message when no service is left of the filters", async () => {
    renderExplorer(config, { search: "nothing" }, []);
    expect(await screen.findByText("serviceList.empty")).toBeInTheDocument();
    // the facets stay usable, because the screen answers the empty view itself
    expect(
      screen.getByRole("button", { name: "serviceList.facets.all" }),
    ).toBeInTheDocument();
  });
});

describe("ServiceListExplorer", () => {
  it("answers the rows of the list while they are loaded", () => {
    renderExplorer(WMS_SERVICE_LIST_CONFIG, {}, [], true);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("lights the facet which a filter of the filter button answers", async () => {
    // the search narrows, a filter of the list narrows and the facet of that
    // state is the one which is chosen - one state, asked in one way
    renderExplorer(WMS_SERVICE_LIST_CONFIG, { has_alert: true });
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
    renderExplorer(WMS_SERVICE_LIST_CONFIG);
    await screen.findByText("Soil data");
    // the columns of the elements and of the last change do not order the list,
    // because the api refuses a sort by them for every kind of service
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

  it("offers the harvesting of a catalogue in its row", async () => {
    renderExplorer(CATALOGUE_SERVICE_LIST_CONFIG, {}, [
      {
        id: "c-1",
        title: "Geo catalogue",
        hits: 5,
        harvestAborted: true,
        harvestFailedAt: "2026-10-01T10:00:00Z",
        elementCount: 128,
      },
      {
        id: "c-2",
        title: "Harvesting catalogue",
        hits: 1,
        runningHarvestingJob: { id: "hj-9" },
      },
    ]);
    const rows = await screen.findAllByRole("row");
    // a catalogue whose last harvesting ended before it was done is marked
    expect(
      within(rows[1] as HTMLElement).getByText(
        "serviceAttention.shortLabels.harvestAborted",
      ),
    ).toBeInTheDocument();
    // the rows are compact, the harvest button of the list is not rendered
    // beside the headline but inside every row of the catalogue
    expect(
      within(rows[1] as HTMLElement).getByText("Harvest"),
    ).toBeInTheDocument();
    // a catalogue whose harvesting runs is asked for the job which runs
    expect(
      within(rows[2] as HTMLElement).getByText("running job"),
    ).toBeInTheDocument();
  });
});
