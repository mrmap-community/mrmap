import {
  AdminContext,
  ResourceContextProvider,
  ResourceDefinitionContextProvider,
  TestMemoryRouter,
  TextField,
  testDataProvider,
  type DataProvider,
} from "react-admin";
import { Route, Routes } from "react-router-dom";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { choiceLabel } from "./RecordFields";
import { relationGraph, relationGroups } from "./RecordRelations";
import RecordShow from "./RecordShow";

// these screens render full react-admin pages and dialogs and need more than the default timeout
vi.setConfig({ testTimeout: 20000 });

vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: ({ operationId }: { operationId: string }) =>
    operationId.includes("Language")
      ? [
          {
            component: TextField,
            props: { source: "value", choices: [{ id: 7, name: "German" }] },
          },
        ]
      : [
          "title",
          "abstract",
          "fileIdentifier",
          "resourceIdentifier",
          "origin",
          "languages",
          "insufficientQuality",
          "accessConstraints",
          "name",
        ].map((source) => ({
          component: TextField,
          props: {
            source,
            label: source,
            ...(source === "origin"
              ? { choices: [{ id: 5, name: "Catalogue harvest" }] }
              : {}),
            ...(source === "languages" ? { reference: "Language" } : {}),
          },
        })),
}));
// the schema answers a historical endpoint only for dataset and service records;
// the changelog tab is gated on exactly that answer
vi.mock("../../../../jsonapi/hooks/useOperation", () => ({
  default: (operationId: string) =>
    operationId === "list_HistoricalApplicationMetadataRecord"
      ? undefined
      : ({}),
}));
vi.mock("../../../../jsonapi/components/ListGuesser", () => ({
  default: ({ resource, filter }: { resource: string; filter?: object }) => (
    <div>
      {resource} {JSON.stringify(filter)}
    </div>
  ),
}));
vi.mock("../../../../jsonapi/components/EditGuesser", () => ({
  default: () => <div>Edit form</div>,
}));
vi.mock("../History/HistoryList", () => ({
  default: () => <div>Record changes</div>,
}));
vi.mock("../../../MapContainer/GeoJsonMap", () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));
vi.mock("../../../Input/FeatureGroupEditor", () => ({
  default: () => <div>Extent map</div>,
}));

const setup = (
  resource = "DatasetMetadataRecord",
  tab = "",
  permissions = false,
  documents = false,
) => {
  const getOne = vi.fn(async () => ({
    data: {
      id: "record-1",
      title: "Parsed record",
      abstract: "Full harvested abstract",
      resourceIdentifier: "namespace:code",
      fileIdentifier: "file-id",
      origin: 5,
      languages: [{ id: 7, value: 7 }],
      canEdit: permissions,
      canDelete: permissions,
      isBroken: true,
      insufficientQuality: "Missing identifier",
      isSearchable: false,
      metadataContact: {
        id: 1,
        name: "Curator",
        email: "curator@example.com",
        phone: "+123",
      },
      datasetContact: { id: 2, name: "Dataset provider" },
      applicationContact: { id: 3, name: "Application provider" },
      accessConstraints: "No constraints",
    },
  }));
  render(
    <TestMemoryRouter
      initialEntries={[`/${resource}/record-1/show${tab ? `/${tab}` : ""}`]}
    >
      <AdminContext
        dataProvider={testDataProvider({
          getOne: getOne as DataProvider["getOne"],
          getList: async () => ({ data: [], total: 0 }),
        })}
      >
        <ResourceDefinitionContextProvider
          definitions={{
            [resource]: {
              name: resource,
              hasShow: true,
              hasEdit: true,
              hasList: true,
              hasCreate: false,
              options: { hasDelete: true },
              recordRepresentation: "title",
            },
          }}
        >
          <ResourceContextProvider value={resource}>
            <Routes>
              <Route
                path={`/${resource}/:id/show/*`}
                element={<RecordShow documents={documents} />}
              />
            </Routes>
          </ResourceContextProvider>
        </ResourceDefinitionContextProvider>
      </AdminContext>
    </TestMemoryRouter>,
  );
  return getOne;
};

describe("record detail pages", () => {
  it("renders harvested identity and schema labels without offering unauthorized actions", async () => {
    setup();
    expect(
      await screen.findByText("Full harvested abstract"),
    ).toBeInTheDocument();
    expect(screen.getByText("German")).toBeInTheDocument();
    expect(screen.getAllByText("Catalogue harvest").length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: "ra.action.edit" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "ra.action.delete" }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("Missing identifier").length).toBeGreaterThan(0);
  });

  it("opens service records on a directly linked spatial tab with honest empty states", async () => {
    const getOne = setup("ServiceMetadataRecord", "spatial");
    expect(
      await screen.findByText("datasetExplorer.missingCoverage"),
    ).toBeInTheDocument();
    expect(screen.getByText("recordShow.noTime")).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "recordShow.spatial" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(getOne.mock.calls[0]).toBeDefined();
  });

  it("shows contact links and usage without an edit form", async () => {
    setup("DatasetMetadataRecord", "contacts");
    expect(await screen.findByText("curator@example.com")).toHaveAttribute(
      "href",
      "mailto:curator@example.com",
    );
    expect(screen.getByText("+123")).toHaveAttribute("href", "tel:+123");
    expect(screen.getByText("No constraints")).toBeInTheDocument();
  });

  it("asks the application answer for its application contact, not for a dataset contact", async () => {
    const getOne = setup("ApplicationMetadataRecord");
    expect(await screen.findByText("Full harvested abstract")).toBeInTheDocument();
    await waitFor(() => expect(getOne).toHaveBeenCalled());
    // dataProvider.getOne(resource, params) - the include rides in params.meta
    const params = (
      getOne.mock.calls[0] as unknown as [string, { meta?: unknown }]
    )[1];
    const meta = JSON.stringify(params.meta);
    expect(meta).toContain("applicationContact");
    expect(meta).not.toContain("datasetContact");
  });
  it("keeps the changelog tab exactly where the schema answers historical records", async () => {
    setup("ApplicationMetadataRecord");
    await screen.findByText("Full harvested abstract");
    expect(
      screen.queryByRole("tab", { name: "recordShow.history" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "recordShow.harvests" }),
    ).toBeInTheDocument();
  });
  it("names the providing contact card after the application record", async () => {
    setup("ApplicationMetadataRecord", "contacts");
    expect(await screen.findByText("recordShow.applicationContact")).toBeInTheDocument();
    expect(
      screen.queryByText("recordShow.datasetContact"),
    ).not.toBeInTheDocument();
  });
  it("opens the documents tab the application screen asks for, honest about a missing file", async () => {
    setup("ApplicationMetadataRecord", "documents", false, true);
    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: "recordShow.documents" }),
      ).toHaveAttribute("aria-selected", "true"),
    );
    expect(
      screen.getByRole("alert").textContent,
    ).toContain("recordShow.noStoredXml");
  });
  it("keeps the documents tab away from the screens which do not ask for it", async () => {
    setup("DatasetMetadataRecord");
    await screen.findByText("Full harvested abstract");
    expect(
      screen.queryByRole("tab", { name: "recordShow.documents" }),
    ).not.toBeInTheDocument();
  });
  it("shows the harvesting relations of the application run by its own record column", async () => {
    setup("ApplicationMetadataRecord", "harvests");
    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: "recordShow.harvests" }),
      ).toHaveAttribute("aria-selected", "true"),
    );
    expect(
      screen.getByText(/HarvestedMetadataRelation/),
    ).toHaveTextContent('"application_metadata_record__id":"record-1"');
  });
  it("opens application relations on the catalogues alone without a metadata relation query", async () => {
    setup("ApplicationMetadataRecord", "relations");
    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: "recordShow.relations" }),
      ).toHaveAttribute("aria-selected", "true"),
    );
    expect(
      screen.queryByText(/MetadataRelation/),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/CatalogueService/)).toBeInTheDocument();
  });

  it("offers an edit form only with permission", async () => {
    setup("ServiceMetadataRecord", "", true);
    const edit = await screen.findByRole("button", { name: "ra.action.edit" });
    fireEvent.click(edit);
    expect(await screen.findByText("Edit form")).toBeInTheDocument();
  });

  it("opens directly linked relations with correctly scoped groups", async () => {
    setup("ServiceMetadataRecord", "relations");
    await waitFor(() =>
      expect(
        screen.getByRole("tab", { name: "recordShow.relations" }),
      ).toHaveAttribute("aria-selected", "true"),
    );
    expect(screen.getByText(/MetadataRelation.*wms__isnull/)).toHaveTextContent(
      '"service_metadata":"record-1"',
    );
  });

  it("builds stable typed, labelled graph edges without node ID collisions", () => {
    const graph = relationGraph(
      { id: "same-id", title: "Metadata" },
      [
        {
          id: 1,
          layer: { id: "same-id", stringRepresentation: "Layer" },
          origin: 5,
        },
        {
          id: 2,
          csw: { id: "same-id", stringRepresentation: "Catalogue" },
          origin: 5,
        },
      ],
      relationGroups("DatasetMetadataRecord"),
      [{ id: 5, name: "Harvest" }],
    );
    expect(new Set(graph.nodes.map((node) => node.id)).size).toBe(3);
    expect(graph.edges.map((edge) => edge.label)).toEqual([
      "Layer · Harvest",
      "CatalogueService · Harvest",
    ]);
    expect(choiceLabel(5, [{ id: "5", name: "Harvest" }])).toBe("Harvest");
  });
  it("includes harvested catalogues in the graph with separate identities", () => {
    const graph = relationGraph(
      {
        id: "record",
        harvestedThrough: [{ id: "csw", title: "Harvest catalogue" }],
      },
      [],
      relationGroups("DatasetMetadataRecord"),
      [],
      "Harvested through",
    );
    expect(graph.nodes[1].data.label).toBe("Harvest catalogue");
    expect(graph.edges[0].label).toBe("Harvested through");
  });
});
