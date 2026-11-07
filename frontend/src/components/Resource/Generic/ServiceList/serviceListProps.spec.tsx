import type { ServiceListConfig } from "./config";

import {
  AdminContext,
  Datagrid,
  ListContextProvider,
  ResourceContextProvider,
  ShowButton,
  WrapperField,
  testDataProvider,
  useList,
} from "react-admin";

import { render, screen, within } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";

import en from "../../../../i18n/en";
import { serviceListProps } from "./serviceListProps";

/** a moment the given days before now - the rows answer relative distances, so
 *  the spec names its moments as distances too */
const daysAgo = (days: number) =>
  new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();

const records = [
  { id: "service-1", title: "Weather WMS", abstract: "Weather maps", elementCount: 24, hasAlert: false },
  { id: "service-2", title: "Orthophotos", abstract: "Regional imagery", elementCount: 12, hasAlert: true, updateReviewRequired: true, updateReviewRequiredAt: daysAgo(3) },
  { id: "service-3", title: "Harvested catalogue", abstract: "Records of the north", elementCount: 7, hasAlert: true, harvestAborted: true, harvestFailedAt: daysAgo(1), runningHarvestingJob: { id: "job-9" } },
];

/** the columns of a catalogue screen answer the harvesting, which no other kind
 *  of service answers - and the config names that with its harvest filters */
const configs: ServiceListConfig[] = [
  { resource: "WebMapService", protocol: "WMS", countLabelKey: "layers", fields: [] },
  { resource: "WebFeatureService", protocol: "WFS", countLabelKey: "featureTypes", fields: [] },
  {
    resource: "CatalogueService",
    protocol: "CSW",
    countLabelKey: "records",
    fields: [],
    harvestFilters: ["harvest_aborted", "harvest_incomplete"],
  },
];

const Columns = ({ config }: { config: ServiceListConfig }) => {
  const list = useList({ data: records, sort: { field: "title", order: "ASC" } });
  return (
    <ListContextProvider value={list}>
      <Datagrid bulkActionButtons={false} rowClick={false}>
        {serviceListProps(config, "en").columns}
        <WrapperField label="ra.list.actions"><ShowButton /></WrapperField>
      </Datagrid>
    </ListContextProvider>
  );
};

const renderList = (config: ServiceListConfig, dataProvider = testDataProvider({})) =>
  render(
    <AdminContext
      i18nProvider={polyglotI18nProvider(() => en, "en")}
      dataProvider={dataProvider}
    >
      <ResourceContextProvider value={config.resource}>
        <Columns config={config} />
      </ResourceContextProvider>
    </AdminContext>,
  );

const headers = () => screen.getAllByRole("columnheader");

const headerOf = (label: string) =>
  headers().find(cell => cell.textContent === label);

/** the cell of the row which answers the named column */
const cellOf = (label: string, row: HTMLElement) =>
  within(row).getAllByRole("cell")[headers().findIndex(cell => cell.textContent === label)];

const rowOf = (title: string) => screen.getByText(title).closest("tr")!;

const countLabel: Record<string, string> = {
  layers: "Layers",
  featureTypes: "Feature types",
  records: "Records",
};

describe("service list columns", () => {
  it.each(configs)("renders the columns $resource answers, in order", config => {
    renderList(config);
    const expected = ["Title", "Abstract", "ID", "Status"];
    // the harvesting is a state of a catalogue and of no other service, so only
    // the catalogue screen carries the column - between status and the count
    if (config.harvestFilters) {
      expected.push("Harvesting");
    }
    expected.push(countLabel[config.countLabelKey], "Last update", "Actions");
    expect(headers().map(cell => cell.textContent)).toEqual(expected);
  });

  it("reads every state of a row from the row itself", () => {
    const getManyReference = vi.fn();
    renderList(
      configs[0],
      testDataProvider({ getManyReference }),
    );
    // no row asks a moment the page already answers by its annotations
    expect(getManyReference).not.toHaveBeenCalled();

    const weather = rowOf("Weather WMS");
    expect(within(weather).getByText("No alerts")).toBeInTheDocument();
    expect(within(weather).getByText("24")).toBeInTheDocument();
    // a row without any update state says so instead of staying blank
    expect(within(cellOf("Last update", weather)).getByText("Nothing reported")).toBeInTheDocument();

    const imagery = rowOf("Orthophotos");
    // the moment of the state is the end of the run which decided it, read from
    // the row and shown by its distance to now
    const lastUpdate = cellOf("Last update", imagery);
    expect(within(lastUpdate).getByText("Review required")).toBeInTheDocument();
    expect(within(lastUpdate).getByText("3 days ago")).toBeInTheDocument();
  });

  it("answers the harvesting of a catalogue from its row", () => {
    renderList(configs[2]);
    const catalogue = rowOf("Harvested catalogue");
    const harvest = cellOf("Harvesting", catalogue);
    expect(within(harvest).getByText("Harvesting aborted")).toBeInTheDocument();
    expect(within(harvest).getByText("yesterday")).toBeInTheDocument();
    // the harvesting which works right now is answered by the row and leads to
    // the job which runs
    expect(within(harvest).getByRole("link", { name: "Show the harvesting" })).toHaveAttribute(
      "href", expect.stringContaining("HarvestingJob/job-9/show"),
    );
    // a catalogue which answers nothing of its harvesting says so
    const weather = rowOf("Weather WMS");
    expect(within(cellOf("Harvesting", weather)).getByText("Nothing reported")).toBeInTheDocument();
  });

  it("orders only by the attributes the api orders services by", () => {
    renderList(configs[2]);
    // the flag of attention and the moment of the failing harvesting are
    // ordering fields of the view (registry/views/service.py); the sortable
    // header answers the attribute it sends to the api by its data-field
    const sortOf = (label: string) =>
      within(headerOf(label)!).queryByRole("button");
    expect(sortOf("Status")).toHaveAttribute("data-field", "hasAlert");
    expect(sortOf("Harvesting")).toHaveAttribute("data-field", "harvestFailedAt");
    // the count of the elements is no ordering field, and the column of the
    // updates answers two annotations - sorting it by one of them would order
    // by a half truth, so it offers nothing
    expect(sortOf(countLabel.records)).toBeNull();
    expect(sortOf("Last update")).toBeNull();
    expect(sortOf("Actions")).toBeNull();
  });
});
