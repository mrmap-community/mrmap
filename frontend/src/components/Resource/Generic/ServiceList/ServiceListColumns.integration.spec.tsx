import {
  AdminContext,
  type GetManyReferenceParams,
  RecordContextProvider,
  ResourceDefinitionContextProvider,
  TextField,
  memoryStore,
  testDataProvider,
} from "react-admin";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "../../../../i18n/en";
import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import { useSelectedRecordContext } from "../../../../jsonapi/components/SelectedRecordContext";
import { CATALOGUE_SERVICE_LIST_CONFIG } from "../../CatalogueService/CatalogueServiceList";
import { serviceListProps } from "./serviceListProps";

const state = vi.hoisted(() => ({ identity: { id: "user-1" } as { id: string } | undefined }));
beforeEach(() => { state.identity = { id: "user-1" }; });
vi.mock("react-admin", async importOriginal => ({
  ...await importOriginal<typeof import("react-admin")>(),
  useGetIdentity: () => ({ data: state.identity }),
}));
vi.mock("../../../../context/HttpClientContext", () => ({ useHttpClientContext: () => ({}) }));
vi.mock("../../../../jsonapi/hooks/useResourceSchema", () => ({ default: () => ({ operation: {} }) }));
vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: () => [{ component: TextField, props: { source: "stringRepresentation" } }],
}));
vi.mock("../../../../jsonapi/hooks/useFilterInputForOperation", () => ({ useFilterInputForOperation: () => [] }));
vi.mock("../../../../jsonapi/hooks/useJsonApiQuery", () => ({ default: () => ({}) }));
vi.mock("../../../../jsonapi/hooks/useOnError", () => ({ default: () => undefined }));

const Selection = () => {
  const { selectedRecord } = useSelectedRecordContext();
  return <aside>{selectedRecord?.title ?? "No selection"}</aside>;
};

const records = [
  {
    id: "0dffc1d3-a60e-49d0-a87c-027a4292a4fb",
    title: "DWD GeoServer WMS",
    abstract: "This is the Web Map Server of DWD.",
    elementCount: 24,
    stringRepresentation: "Generated field must be replaced",
  },
  {
    id: "c67b239d-bd95-4dbe-a48a-0e6a34cd1be1",
    title: "WMS RP DOP20",
    abstract: "Web Map Service von Rheinland-Pfalz der Digitalen Orthophotos (DOP) – Dienst für entzerrte Luftbilder.",
    elementCount: 12,
    updateReviewRequired: true,
  },
];

describe("service columns in ListGuesser", () => {
  it("offers immediate harvesting and service-scoped schedule actions in CSW rows", async () => {
    const create = vi.fn().mockResolvedValue({ data: { id: "harvest-1" } });
    render(
      <AdminContext
        i18nProvider={polyglotI18nProvider(() => en, "en")}
        store={memoryStore()}
        dataProvider={testDataProvider({
          getList: vi.fn().mockResolvedValue({ data: [
            { id: "new", title: "New catalogue", periodicHarvestingJobs: [] },
            { id: "scheduled", title: "Scheduled catalogue", periodicHarvestingJobs: [{ id: "schedule-1" }] },
            { id: "running", title: "Running catalogue", periodicHarvestingJobs: [], runningHarvestingJob: { id: "active-harvest" } },
          ], total: 3 }),
          getManyReference: vi.fn().mockResolvedValue({ data: [], total: 0 }),
          create,
        })}
      >
        <ResourceDefinitionContextProvider definitions={{
          CatalogueService: { name: "CatalogueService", hasList: true, hasShow: true, hasEdit: true, hasCreate: false },
          HarvestingJob: { name: "HarvestingJob", hasShow: true, hasCreate: true },
          PeriodicHarvestingJob: { name: "PeriodicHarvestingJob", hasList: true, hasCreate: true },
        }}>
          <ListGuesser
            {...serviceListProps(CATALOGUE_SERVICE_LIST_CONFIG)}
            resource="CatalogueService"
            aside={<Selection />}
            filters={[]}
            actions={false}
            disableAuthentication
            disableSyncWithLocation
          />
        </ResourceDefinitionContextProvider>
      </AdminContext>,
    );

    const newRow = (await screen.findByText("New catalogue")).closest("tr")!;
    const scheduledRow = screen.getByText("Scheduled catalogue").closest("tr")!;
    const runningRow = screen.getByText("Running catalogue").closest("tr")!;
    expect(within(newRow).getByRole("link", { name: "Create harvesting schedule" })).toHaveAttribute(
      "href", "#/CatalogueService/new/show/PeriodicHarvestingJob/create",
    );
    expect(within(scheduledRow).getByRole("link", { name: "Configure harvesting schedules" })).toHaveAttribute(
      "href", "#/CatalogueService/scheduled/show/PeriodicHarvestingJob",
    );
    expect(within(scheduledRow).queryByRole("link", { name: "Create harvesting schedule" })).not.toBeInTheDocument();
    expect(within(runningRow).getByRole("link", { name: "View running harvest" })).toHaveAttribute(
      "href", "#/HarvestingJob/active-harvest/show",
    );
    expect(within(runningRow).queryByRole("button", { name: "Harvest now" })).not.toBeInTheDocument();
    fireEvent.click(within(newRow).getByRole("button", { name: "Harvest now" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith("HarvestingJob", expect.objectContaining({
      data: { service: { id: "new" } },
    })));
    expect(screen.getByRole("complementary")).toHaveTextContent("No selection");
  });

  it.each(["anonymous", "unavailable"])("hides schedule creation when %s", reason => {
    state.identity = reason === "anonymous" ? undefined : { id: "user-1" };
    const Actions = CATALOGUE_SERVICE_LIST_CONFIG.RowAction!;
    render(
      <AdminContext i18nProvider={polyglotI18nProvider(() => en, "en")}>
        <ResourceDefinitionContextProvider definitions={{
          PeriodicHarvestingJob: { name: "PeriodicHarvestingJob", hasCreate: reason !== "unavailable" },
        }}>
          <RecordContextProvider value={{ id: "new", periodicHarvestingJobs: [] }}>
            <Actions />
          </RecordContextProvider>
        </ResourceDefinitionContextProvider>
      </AdminContext>,
    );
    expect(screen.queryByRole("link", { name: "Create harvesting schedule" })).not.toBeInTheDocument();
  });

  it("keeps the configured columns and row selection despite stored generated-column preferences", async () => {
    const props = serviceListProps({ resource: "WebMapService", protocol: "WMS", countLabelKey: "layers", fields: ["title", "abstract", "element_count"] });
    render(
      <AdminContext
        i18nProvider={polyglotI18nProvider(() => en, "en")}
        store={memoryStore({
          "preferences.list_WebMapService.datagrid.columns": ["0"],
          "preferences.list_WebMapService.datagrid.omit": ["elementCount"],
        })}
        dataProvider={testDataProvider({
          getList: vi.fn().mockResolvedValue({ data: records, total: records.length }),
          getManyReference: vi.fn().mockImplementation(async (_resource: string, params: GetManyReferenceParams) => ({
            data: [{ id: `job-${params.id}`, doneAt: "2026-10-07T12:15:00Z", status: params.id === records[0].id ? "Succeeded" : "Failed" }],
            total: 1,
          })),
        })}
      >
        <ResourceDefinitionContextProvider definitions={{
          WebMapService: { name: "WebMapService", hasList: true, hasShow: true, hasEdit: true, hasCreate: false },
        }}>
          <ListGuesser
            {...props}
            resource="WebMapService"
            header={<h1>Web Map Services</h1>}
            aside={<Selection />}
            filters={[]}
            actions={false}
            disableAuthentication
            disableSyncWithLocation
          />
        </ResourceDefinitionContextProvider>
      </AdminContext>,
    );

    expect(await screen.findByText("DWD GeoServer WMS")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("columnheader").map(cell => cell.textContent)).toEqual([
      "Title", "Abstract", "ID", "Status", "Layers", "Last update", "Actions",
    ]));
    expect(screen.queryByText("Generated field must be replaced")).not.toBeInTheDocument();
    expect(await screen.findByText("Succeeded")).toBeInTheDocument();
    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
    const row = screen.getByText("DWD GeoServer WMS").closest("tr")!;
    expect(within(row).getByRole("link", { name: "Show" })).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: "Edit" })).toBeInTheDocument();
    fireEvent.click(screen.getByText("DWD GeoServer WMS"));
    expect(screen.getByRole("complementary")).toHaveTextContent("DWD GeoServer WMS");
  });
});
