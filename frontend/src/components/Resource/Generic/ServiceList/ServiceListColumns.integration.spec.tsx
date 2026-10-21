import {
  AdminContext,
  type GetManyReferenceParams,
  ResourceDefinitionContextProvider,
  TextField,
  memoryStore,
  testDataProvider,
} from "react-admin";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";

import en from "../../../../i18n/en";
import ListGuesser from "../../../../jsonapi/components/ListGuesser";
import { useSelectedRecordContext } from "../../../../jsonapi/components/SelectedRecordContext";
import { serviceListProps } from "./serviceListProps";

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
