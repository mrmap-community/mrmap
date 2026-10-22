import {
  AdminContext,
  type ListControllerResult,
  ListContextProvider,
  ResourceContextProvider,
  testDataProvider,
} from "react-admin";

import { QueryClient } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "../../../../i18n/en";
import { type ServiceListResource } from "./config";
import ServiceSummaryTiles, {
  filterOfTile,
  summaryTiles,
} from "./ServiceSummaryTiles";

import "@testing-library/jest-dom/vitest";

/**
 * The tiles above the list of the registered services.
 *
 * A tile answers a count of the api, so what a spec asks is which filters a tile
 * is counted by and which list its link opens - the number itself is the answer
 * of the api and nothing the screen calculates.
 */

/**
 * The filter a list of services applies on its own - only the lists of web map
 * services and of web feature services filter the update candidates out, which
 * jsonapi/components/ListGuesser.tsx decides.
 */
const ownFilterOf = (resource: ServiceListResource): Record<string, unknown> =>
  resource === "CatalogueService" ? {} : { is_update_candidate: false };

/** the label a tile is translated by, as the english translation answers it */
const LABELS: Record<string, string> = {
  total: "Services in this view",
  noAlerts: "No alerts",
  runningUpdates: "Updates running (all services)",
  needsAttention: "Needs attention",
};

const getList = vi.fn();
const dataProvider = testDataProvider({ getList });

/**
 * A query client of its own per test, so a count of one test is not the cached
 * answer of another, and so a count which the api refuses is answered as refused
 * at once: the client of the application asks a count which was refused again
 * several times before it gives up an answer, which a spec does not wait for.
 */
let queryClient: QueryClient;

/**
 * The tiles above a list of services which answers the given query.
 *
 * The list controller answers the filter the list applies on its own and the
 * filters a user chose apart, exactly like the controller of a real list does.
 */
const renderTiles = (
  resource: ServiceListResource,
  filter: Record<string, unknown> = {},
  filterValues: Record<string, unknown> = {},
) =>
  render(
    <AdminContext
      dataProvider={dataProvider}
      i18nProvider={polyglotI18nProvider(() => en, "en")}
      queryClient={queryClient}
    >
      <ResourceContextProvider value={resource}>
        <ListContextProvider
          value={
            {
              data: [],
              total: 0,
              isPending: false,
              isFetching: false,
              isEmpty: true,
              error: null,
              resource,
              filter,
              filterValues,
              displayedFilters: {},
              setFilters: vi.fn(),
              sort: { field: "title", order: "ASC" },
              setSort: vi.fn(),
              setPage: vi.fn(),
              page: 1,
              perPage: 25,
              refetch: vi.fn(),
            } as unknown as ListControllerResult
          }
        >
          <ServiceSummaryTiles />
        </ListContextProvider>
      </ResourceContextProvider>
    </AdminContext>,
  );

/** the filters the given resource was counted by, in the order of the tiles */
const filtersOf = (resource: string): Record<string, unknown>[] =>
  getList.mock.calls
    .filter(([counted]) => counted === resource)
    .map(([, params]) => params.filter);

/** the list the link of the tile with the given label opens */
const linkedList = (label: string) => {
  const link = within(
    screen.getByText(label).parentElement as HTMLElement,
  ).getByRole("link");
  const [path, search] = (link.getAttribute("href") ?? "#")
    .replace(/^#\/?/, "")
    .split("?");
  return {
    resource: path,
    filter: JSON.parse(
      new URLSearchParams(search ?? "").get("filter") ?? "{}",
    ),
  };
};

beforeEach(() => {
  getList.mockReset();
  getList.mockResolvedValue({ data: [], total: 0 });
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
});

describe("ServiceSummaryTiles", () => {
  it("names every tile by the state and the scope it counts", async () => {
    renderTiles("WebMapService");
    expect(await screen.findByText("Services in this view")).toBeInTheDocument();
    expect(screen.getByText("No alerts")).toBeInTheDocument();
    expect(
      screen.getByText("Updates running (all services)"),
    ).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    // has_alert is false for a service whose monitoring never ran as it is for a
    // service which passed its last run, so no tile may promise a health
    expect(screen.queryByText("Healthy")).toBeNull();
    // the scope of every tile is explained, so a number of the registry is not
    // read as a number of this view
    const hints: Record<string, string> = en.serviceList.tiles.hints;
    for (const tile of summaryTiles("WebMapService")) {
      expect(hints[tile.key]).toBeTruthy();
    }
  });

  it.each(["WebMapService", "WebFeatureService", "CatalogueService"])(
    "counts the services of the query of the %s list",
    async (resource) => {
      const own = ownFilterOf(resource as ServiceListResource);
      renderTiles(resource as ServiceListResource, own, {
        search: "soil",
        has_alert: true,
        monitoring_failed_at: "2026-10-01",
      });
      await screen.findByText("Services in this view");
      // the search and the filter of the list itself stay with every tile and
      // only the states of attention are answered by the state of the tile
      // alone, which is what makes a tile answer the services of the rows
      expect(filtersOf(resource)).toEqual([
        { ...own, search: "soil" },
        { ...own, search: "soil", has_alert: false },
        { ...own, search: "soil", has_alert: true },
      ]);
    },
  );

  it("counts the running updates of the registry and not of the view", async () => {
    renderTiles("WebMapService", ownFilterOf("WebMapService"), {
      search: "soil",
      bbox_lat_lon__intersects: "POLYGON((6 49,7 49,7 50,6 50,6 49))",
    });
    await screen.findByText("Updates running (all services)");
    // a background process does not name the kind of the service it updates, so
    // no filter of the services is asked of it - the count would answer a
    // question no list on the screen asks
    expect(filtersOf("BackgroundProcess")).toEqual([
      { status: "pending,running", process_type: "update" },
    ]);
  });

  it("links every tile to the results it counts", async () => {
    renderTiles("WebMapService", ownFilterOf("WebMapService"), {
      search: "soil",
    });
    await screen.findByText("Services in this view");
    const scope = { ...ownFilterOf("WebMapService"), search: "soil" };
    for (const tile of summaryTiles("WebMapService")) {
      expect(linkedList(LABELS[tile.key])).toEqual({
        resource: tile.resource,
        filter: filterOfTile(tile, scope),
      });
    }
  });

  it("waits with a count the api did not answer yet", async () => {
    getList.mockReturnValue(new Promise(() => undefined));
    renderTiles("WebMapService");
    await screen.findByText("Needs attention");
    // nothing is counted as none while the answer is out, because a service
    // which is not answered yet is not a service without an alert
    expect(screen.queryByText(/^[0-9]+$/)).toBeNull();
  });

  it("marks a count the api refuses instead of counting it as none", async () => {
    getList.mockRejectedValue(new Error("Forbidden"));
    renderTiles("WebMapService");
    await screen.findByText("Services in this view");
    expect((await screen.findAllByTitle("error")).length).toBeGreaterThan(0);
    expect(screen.queryByText(/^0$/)).toBeNull();
  });
});
