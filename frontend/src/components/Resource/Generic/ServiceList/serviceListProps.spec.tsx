import { render, screen, waitFor, within } from "@testing-library/react";
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
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";
import en from "../../../../i18n/en";
import type { ServiceListConfig } from "./config";
import { serviceListProps } from "./serviceListProps";

const records = [
  { id: "service-1", title: "Weather WMS", abstract: "Weather maps", elementCount: 24, hasAlert: false },
  { id: "service-2", title: "Orthophotos", abstract: "Regional imagery", elementCount: 12, hasAlert: true, updateReviewRequired: true },
];

const Columns = ({ config }: { config: ServiceListConfig }) => {
  const list = useList({ data: records, sort: { field: "title", order: "ASC" } });
  return (
    <ListContextProvider value={list}>
      <Datagrid bulkActionButtons={false} rowClick={false}>
        {serviceListProps(config).columns}
        <WrapperField label="ra.list.actions"><ShowButton /></WrapperField>
      </Datagrid>
    </ListContextProvider>
  );
};

const configs: ServiceListConfig[] = [
  { resource: "WebMapService", protocol: "WMS", countLabelKey: "layers", fields: [] },
  { resource: "WebFeatureService", protocol: "WFS", countLabelKey: "featureTypes", fields: [] },
  { resource: "CatalogueService", protocol: "CSW", countLabelKey: "records", fields: [] },
];

describe("service list columns", () => {
  it.each(configs)("renders ordered columns and service-scoped update jobs for $resource", async config => {
    const getManyReference = vi.fn().mockImplementation(async (_resource, params) => ({
      data: [{ id: `job-${params.id}`, doneAt: "2026-10-07T12:15:00Z", status: params.id === "service-1" ? "Succeeded" : "Failed" }],
      total: 1,
    }));
    render(
      <AdminContext
        i18nProvider={polyglotI18nProvider(() => en, "en")}
        dataProvider={testDataProvider({ getManyReference })}
      >
        <ResourceContextProvider value={config.resource}>
          <Columns config={config} />
        </ResourceContextProvider>
      </AdminContext>,
    );

    expect(screen.getAllByRole("columnheader").map(cell => cell.textContent)).toEqual([
      "Title", "Abstract", "ID", "Status",
      { layers: "Layers", featureTypes: "Feature types", records: "Records" }[config.countLabelKey],
      "Last update", "Actions",
    ]);
    const weather = screen.getByText("Weather WMS").closest("tr")!;
    const imagery = screen.getByText("Orthophotos").closest("tr")!;
    expect(within(weather).getByText("24")).toBeInTheDocument();
    expect(within(weather).getByText("Healthy")).toBeInTheDocument();
    expect(within(imagery).getByText("Review required")).toBeInTheDocument();
    expect(await within(weather).findByText("Succeeded")).toBeInTheDocument();
    expect(await within(imagery).findByText("Failed")).toBeInTheDocument();
    expect(within(weather).getByRole("link", { name: "Show" })).toBeInTheDocument();
    await waitFor(() => {
      for (const service of records) {
        expect(getManyReference).toHaveBeenCalledWith(`${config.resource}UpdateJob`, expect.objectContaining({
          id: service.id,
          target: "service",
          pagination: { page: 1, perPage: 1 },
          sort: { field: "doneAt", order: "DESC" },
          filter: { service: service.id, done_at__isnull: false },
        }));
      }
    });
  });

  it("shows an explicit empty state when no completed update exists", async () => {
    render(
      <AdminContext
        i18nProvider={polyglotI18nProvider(() => en, "en")}
        dataProvider={testDataProvider({ getManyReference: async () => ({ data: [], total: 0 }) })}
      >
        <ResourceContextProvider value="WebMapService">
          <Columns config={configs[0]} />
        </ResourceContextProvider>
      </AdminContext>,
    );
    await waitFor(() => expect(screen.getAllByText("No updates yet")).toHaveLength(2));
  });
});
