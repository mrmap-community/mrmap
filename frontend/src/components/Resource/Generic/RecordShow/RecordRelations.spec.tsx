import {
  AdminContext,
  RecordContextProvider,
  ResourceContextProvider,
  ResourceDefinitionContextProvider,
  TestMemoryRouter,
  testDataProvider,
  type DataProvider,
  type RaRecord,
} from "react-admin";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import i18nProvider from "../../../../providers/i18nProvider";
import RecordRelations, {
  TakeBackButton,
  declarableGroups,
  filledGroups,
  groupFilter,
  recordColumn,
  recordSource,
  relationGraph,
  relationGroups,
} from "./RecordRelations";

vi.mock("../../../../jsonapi/components/ListGuesser", () => ({
  default: ({ resource, filter }: { resource: string; filter?: object }) => (
    <div>
      {resource} {JSON.stringify(filter)}
    </div>
  ),
}));
vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: () => [
    {
      component: () => <span>origin</span>,
      props: { source: "origin", choices: [{ id: 5, name: "Catalogue" }] },
    },
  ],
}));
vi.mock("@xyflow/react", () => ({
  ReactFlow: () => <div data-testid="graph" />,
  Background: () => null,
  Controls: () => null,
}));

// which MetadataRelation column a row fills is the whole statement of the table,
// so the fixture answers the counts the way the api does: one total for the record
// and one per column asked for with its `__isnull` term
const answer = (
  filter: Record<string, unknown> | undefined,
  rows: RaRecord[],
  perColumn: Record<string, number>,
  recordTotal: number,
) => {
  const column = Object.keys(filter ?? {}).find((key) =>
    key.endsWith("__isnull"),
  );
  if (column === undefined) return { data: rows, total: recordTotal };
  const count = perColumn[column.replace("__isnull", "")] ?? 0;
  return { data: count ? rows.slice(0, 1) : [], total: count };
};

const setup = (
  resource: string,
  record: RaRecord,
  rows: RaRecord[] = [],
  perColumn: Record<string, number> = { layer: 2 },
  recordTotal = 2,
  options: { readOnly?: boolean } = {},
) => {
  const getList = vi.fn(async (_resource: string, params: { filter?: Record<string, unknown> }) =>
    answer(params?.filter, rows, perColumn, recordTotal),
  );
  render(
    <TestMemoryRouter initialEntries={[`/${resource}/${String(record.id)}/show`]}>
      <AdminContext
        i18nProvider={i18nProvider}
        dataProvider={testDataProvider({
          getList: getList as DataProvider["getList"],
        })}
      >
        <ResourceDefinitionContextProvider
          definitions={{
            [resource]: {
              name: resource,
              hasShow: true,
              hasList: true,
              options: {},
            },
            // the screen's create and its relation tables read this resource,
            // like every resource the api answers and MrMapFrontend registers
            MetadataRelation: {
              name: "MetadataRelation",
              hasShow: false,
              hasList: true,
              hasCreate: true,
              hasEdit: false,
              options: { type: "MetadataRelation" },
            },
          }}
        >
          <ResourceContextProvider value={resource}>
            <RecordContextProvider value={record}>
              {/* the body of the relations tab, as RecordShow renders it */}
              <RecordRelations readOnly={options.readOnly} />
            </RecordContextProvider>
          </ResourceContextProvider>
        </ResourceDefinitionContextProvider>
      </AdminContext>
    </TestMemoryRouter>,
  );
  return getList;
};

const datasetRecord: RaRecord = {
  id: "dataset-1",
  title: "Soil of the region",
  harvestedThrough: [],
};
const serviceRecord: RaRecord = {
  id: "service-1",
  title: "Service metadata of the WMS",
  harvestedThrough: [],
};

describe("the meaning of a relation is the filled column", () => {
  it("reads the groups of a record out of its rows", () => {
    expect(
      filledGroups([
        { id: 1, wms: { id: "w" } },
        { id: 2, layer: { id: "l" } },
      ]).map((group) => group.source),
    ).toEqual(["layer", "wms"]);
  });

  it("names no group for a column no row fills", () => {
    expect(filledGroups([{ id: 1, layer: { id: "l" } }])).toHaveLength(1);
    expect(filledGroups([])).toEqual([]);
  });

  it("asks the column which holds the record itself", () => {
    expect(recordColumn("DatasetMetadataRecord")).toBe("dataset_metadata");
    expect(recordColumn("ServiceMetadataRecord")).toBe("service_metadata");
    // the application record has no column, so it has no relation query to ask
    expect(recordColumn("ApplicationMetadataRecord")).toBeUndefined();
  });

  it("names the feature type group as the api declares it", () => {
    expect(
      groupFilter("service_metadata", "record-1", {
        source: "featureType",
        filter: "feature_type",
        resource: "FeatureType",
      }),
    ).toEqual({ service_metadata: "record-1", feature_type__isnull: false });
  });

  // the pair of two metadata records is the second sentence the table can state,
  // and both screens write the very same row (#985)
  it("adds the other kind of record as the pair group of a record screen", () => {
    expect(
      relationGroups("DatasetMetadataRecord").map((group) => group.source),
    ).toEqual([
      "layer",
      "featureType",
      "wms",
      "wfs",
      "csw",
      "serviceMetadata",
    ]);
    expect(relationGroups("DatasetMetadataRecord")[5]).toMatchObject({
      source: "serviceMetadata",
      // the pair row is one row for both screens, but only the service record
      // publishes it, so the two ends state it in opposite directions
      operator: "partner",
    });
    expect(relationGroups("ServiceMetadataRecord")[5]).toMatchObject({
      source: "datasetMetadata",
      filter: "dataset_metadata",
      resource: "DatasetMetadataRecord",
      kind: "record",
      operator: "own",
    });
    // a kind without a column of its own has no pair to ask for
    expect(relationGroups("Layer")).toHaveLength(5);
    expect(recordSource("ServiceMetadataRecord")).toBe("serviceMetadata");
  });

  it("asks the pair group by the partner column of the row", () => {
    const partner = relationGroups("DatasetMetadataRecord")[5];
    expect(groupFilter("dataset_metadata", "record-1", partner)).toEqual({
      dataset_metadata: "record-1",
      service_metadata__isnull: false,
    });
    expect(filledGroups([{ id: 1, serviceMetadata: { id: "s" } }], [partner]))
      .toHaveLength(1);
  });

  it("offers to declare only what the model can store", () => {
    // D5 of docs/metadata-identity.md, answered by the api with a 400 for
    // anything else — the screen never shows a choice the row cannot hold
    expect(
      declarableGroups("DatasetMetadataRecord").map((group) => group.source),
    ).toEqual(["layer", "featureType", "serviceMetadata"]);
    expect(
      declarableGroups("ServiceMetadataRecord").map((group) => group.source),
    ).toEqual([
      "layer",
      "featureType",
      "wms",
      "wfs",
      "csw",
      "datasetMetadata",
    ]);
    expect(declarableGroups("Layer")).toEqual([]);
    expect(declarableGroups("ApplicationMetadataRecord")).toEqual([]);
  });

  it("labels an edge with what the coupling asserts", () => {
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
      (resource) => `describes ${resource}`,
      [{ id: 5, name: "Catalogue" }],
    );
    // one node per coupling beside the record itself, without id collisions
    expect(new Set(graph.nodes.map((node) => node.id)).size).toBe(3);
    expect(graph.edges.map((edge) => edge.label)).toEqual([
      "describes Layer · Catalogue",
      "describes CatalogueService · Catalogue",
    ]);
  });

  it("keeps the provenance of a harvest apart from a coupling", () => {
    const graph = relationGraph(
      {
        id: "record",
        harvestedThrough: [{ id: "csw", title: "Harvest catalogue" }],
      },
      [],
      undefined,
      [],
      "Harvested through",
    );
    expect(graph.nodes[1].data.label).toBe("Harvest catalogue");
    expect(graph.edges[0].label).toBe("Harvested through");
  });

  it("draws a pair with the sentence of the pair, not of a description", () => {
    const groups = [
      {
        source: "datasetMetadata",
        filter: "dataset_metadata",
        resource: "DatasetMetadataRecord",
        kind: "record" as const,
        edge: "operates on DatasetMetadataRecord",
      },
    ];
    const graph = relationGraph(
      { id: "service", title: "Service" },
      [{ id: 1, datasetMetadata: { id: "d", title: "Dataset" }, origin: 4 }],
      (resource) => `describes ${resource}`,
      [{ id: 4, name: "Editor" }],
      "Harvested through",
      groups,
    );
    expect(graph.edges[0].label).toBe(
      "operates on DatasetMetadataRecord · Editor",
    );
  });
});

describe("the take back of a declared row", () => {
  const renderRow = (row: RaRecord) =>
    render(
      <TestMemoryRouter>
        <AdminContext
          i18nProvider={i18nProvider}
          dataProvider={testDataProvider({})}
        >
          <ResourceContextProvider value="MetadataRelation">
            <RecordContextProvider value={row}>
              <TakeBackButton />
            </RecordContextProvider>
          </ResourceContextProvider>
        </AdminContext>
      </TestMemoryRouter>,
    );

  it("offers nothing for a coupling the harvest declared", () => {
    // the document which stated the coupling owns it: the api answers 403 and
    // the screen states no promise it cannot keep (D7)
    renderRow({ id: 1, origin: 5, isInternal: false, isPublishable: false });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers the take back for the row a curator declared", () => {
    renderRow({ id: 2, origin: 4, isInternal: true, isPublishable: true });
    expect(
      screen.getByRole("button", { name: /take back/i }),
    ).toBeInTheDocument();
  });
});

describe("the relations tab of a record", () => {
  it("shows what a service record describes, not only its services", async () => {
    // the two-way branch this replaced asked a service record for its services and
    // its catalogue alone, so a coupling to a layer stayed invisible (#1268)
    const getList = setup(
      "ServiceMetadataRecord",
      serviceRecord,
      [{ id: 1, layer: { id: "layer-1", title: "Soil" }, origin: 5 }],
      { layer: 2 },
    );
    expect(await screen.findByText("describes Layer")).toBeInTheDocument();
    // once every column of the table has been asked, what is not on the screen was
    // counted empty and not merely left unasked
    await waitFor(() => expect(getList.mock.calls.length).toBeGreaterThanOrEqual(6));
    expect(screen.getByText(/MetadataRelation/).textContent).toContain(
      '"service_metadata":"service-1","layer__isnull":false',
    );
    expect(
      screen.queryByText("describes WebMapService"),
    ).not.toBeInTheDocument();
  });

  it("counts every group by the query of that group", async () => {
    const getList = setup(
      "DatasetMetadataRecord",
      datasetRecord,
      [{ id: 1, layer: { id: "l" } }],
      { layer: 2, feature_type: 4 },
      6,
    );
    expect(await screen.findByText("2 relations")).toBeInTheDocument();
    await waitFor(() => expect(getList.mock.calls.length).toBeGreaterThanOrEqual(6));
    expect(screen.getByText("4 relations")).toBeInTheDocument();
    expect(screen.getByText("describes FeatureType")).toBeInTheDocument();
    // a column no row fills is no group of this record and is never shown empty
    expect(
      screen.queryByText("describes CatalogueService"),
    ).not.toBeInTheDocument();
  });

  it("says honestly that nothing is stored, beside the catalogues it came from", async () => {
    setup("DatasetMetadataRecord", datasetRecord, [], {}, 0);
    expect(
      await screen.findByText("No relation is stored for this record."),
    ).toBeInTheDocument();
    // the provenance of the record keeps its answer: being harvested neither
    // proves nor disproves a coupling
    expect(screen.getByText(/CatalogueService/)).toBeInTheDocument();
    expect(screen.queryByText(/recordShow\./)).not.toBeInTheDocument();
  });

  it("asks no relation query for a record kind without a column", async () => {
    setup(
      "ApplicationMetadataRecord",
      { id: "app-1", title: "Application", harvestedThrough: [] },
      [],
      {},
      0,
    );
    expect(await screen.findByText(/CatalogueService/)).toBeInTheDocument();
    expect(screen.queryByText(/MetadataRelation/)).not.toBeInTheDocument();
    expect(
      screen.queryByText("No relation is stored for this record."),
    ).not.toBeInTheDocument();
  });

  it("continues the group of a graph in the table of that group", async () => {
    setup(
      "DatasetMetadataRecord",
      datasetRecord,
      [{ id: 1, layer: { id: "l" }, origin: 5 }],
      { layer: 2, feature_type: 4 },
      6,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Graph" }));
    await waitFor(() =>
      expect(screen.getByText("2 relations")).toBeInTheDocument(),
    );
    // the budget of the graph is stated with the real total behind it (#1268)
    expect(
      await screen.findByText(/The graph draws 1 of 6 relations/),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getAllByRole("button", { name: /show all of this group/i })[0],
    );
    await waitFor(() =>
      expect(screen.getAllByText("2 relations")).toHaveLength(1),
    );
    const tables = screen.getAllByText(/MetadataRelation/);
    expect(tables).toHaveLength(1);
    expect(tables[0].textContent).toContain('"layer__isnull":false');
  });

  it("groups the pair of a record beside the elements it describes", async () => {
    // the row of the pair fills the partner column, so the group of the pair
    // appears with its own sentence and its own query (#985)
    setup(
      "DatasetMetadataRecord",
      datasetRecord,
      [{ id: 1, serviceMetadata: { id: "s", title: "Service" }, origin: 4 }],
      { layer: 2, service_metadata: 1 },
      3,
    );
    expect(
      await screen.findByText("operated on by ServiceMetadataRecord"),
    ).toBeInTheDocument();
    const tables = screen.getAllByText(/MetadataRelation/);
    expect(
      tables.some(
        (table) =>
          (table.textContent ?? "").includes(
            '"dataset_metadata":"dataset-1","service_metadata__isnull":false',
          ),
      ),
    ).toBe(true);
  });

  it("offers the declaration of a coupling where a coupling can stand", async () => {
    // the record which stores nothing yet is exactly the one a coupling is
    // worth declaring for, so the offer is not gated on an existing row
    setup("DatasetMetadataRecord", datasetRecord, [], {}, 0);
    expect(
      await screen.findByRole("button", { name: /declare a relation/i }),
    ).toBeInTheDocument();
  });

  it("declares nothing for a kind which can store no coupling", async () => {
    setup(
      "ApplicationMetadataRecord",
      { id: "app-1", title: "Application", harvestedThrough: [] },
      [{ id: 1, layer: { id: "l" } }],
      { layer: 2 },
      2,
    );
    await screen.findByText(/CatalogueService/);
    // the offer follows the matrix of the model, not the emptiness of a screen
    expect(
      screen.queryByRole("button", { name: /declare a relation/i }),
    ).not.toBeInTheDocument();
  });

  it("states no declaration and no take back while read-only", async () => {
    // the record editor's pane says relations belong to the record's own page,
    // and shows exactly that (#985)
    setup("DatasetMetadataRecord", datasetRecord, [], {}, 0, {
      readOnly: true,
    });
    expect(
      await screen.findByText("No relation is stored for this record."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /declare a relation/i }),
    ).not.toBeInTheDocument();
  });
});
