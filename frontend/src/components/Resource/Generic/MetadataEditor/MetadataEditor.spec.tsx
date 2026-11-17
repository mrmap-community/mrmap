import {
  AdminContext,
  ResourceDefinitionContextProvider,
  TestMemoryRouter,
  testDataProvider,
  TextInput,
  type DataProvider,
} from "react-admin";
import { Route, Routes } from "react-router-dom";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MetadataEditorRoute from "./MetadataEditorRoute";

// the editor renders whole pages against the schema layer; the specs mock
// that layer the way RecordShow.spec does and keep the editor logic real
vi.setConfig({ testTimeout: 20000 });

vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: () =>
    [
      "title",
      "abstract",
      "lineStatement",
      "keywords",
      "dateType",
      "origin",
    ].map((source) => ({
      component: TextInput,
      props: {
        source,
        label: source,
        ...(source === "origin" ? { disabled: true } : {}),
      },
    })),
}));
// only the dataset record is a known kind, with a changelog endpoint
vi.mock("../../../../jsonapi/hooks/useOperation", () => ({
  default: (operationId?: string) =>
    operationId === "retrieve_DatasetMetadataRecord" ||
    operationId === "list_HistoricalDatasetMetadataRecord"
      ? {}
      : undefined,
}));
vi.mock("../../../../jsonapi/hooks/useResourceSchema", () => ({
  default: () => ({
    schema: {
      properties: {
        attributes: {
          properties: {
            title: {
              type: "string",
              "x-iso-path":
                "/MD_Metadata/identificationInfo/MD_DataIdentification/citation/title",
            },
            abstract: {
              type: "string",
              "x-iso-path":
                "/MD_Metadata/identificationInfo/MD_DataIdentification/abstract",
            },
            lineStatement: { type: "string" },
            dateType: { type: "string" },
          },
        },
        relationships: {
          properties: {
            keywords: {
              properties: { data: { type: "array" } },
            },
          },
        },
      },
    },
    includeAbleResources: ["profile", "metadataContact"],
    sparseFieldsPerResource: undefined,
  }),
}));
// the reused read-only cards render whole RecordShow subsystems; the editor
// only has to place them, their own specs cover what they show
vi.mock("../RecordShow/RecordContacts", () => ({
  default: () => <div>Contacts card</div>,
}));
vi.mock("../RecordShow/RecordRelations", () => ({
  default: () => <div>Relations card</div>,
}));
vi.mock("../RecordShow/RecordHistory", () => ({
  default: ({ harvests }: { harvests?: boolean }) => (
    <div>{harvests ? "Harvests card" : "Changes card"}</div>
  ),
}));

const makeRecord = (overrides: object = {}) => ({
  id: "record-1",
  title: "",
  abstract: "",
  allowedActions: ["view", "change"],
  isSearchable: false,
  profile: {
    id: "p1",
    name: "iso19139",
    label: "ISO 19139 metadata",
    sections: [
      {
        id: "identification",
        label: "Identification",
        fields: [
          { field: "title", requirement: "mandatory" },
          { field: "abstract", requirement: "recommended" },
          { field: "lineStatement", requirement: "optional" },
        ],
      },
    ],
    rules: [
      {
        id: "R1",
        family: "identifiers",
        severity: "error",
        field: "title",
        assert: "normalize-space(.)",
        message: "A title is required.",
      },
    ],
  },
  ...overrides,
});

const setup = (type = "DatasetMetadataRecord", record = makeRecord()) => {
  render(
    <TestMemoryRouter initialEntries={[`/metadata/${type}/record-1/edit`]}>
      <AdminContext
        dataProvider={
          testDataProvider({
            getOne: (async () => ({ data: record })) as DataProvider["getOne"],
          })
        }
      >
        <ResourceDefinitionContextProvider
          definitions={{
            [type]: {
              name: type,
              hasShow: true,
              hasEdit: true,
              hasList: true,
              hasCreate: false,
              options: {},
              recordRepresentation: "title",
            },
          }}
        >
          <Routes>
            <Route path="/metadata/:type/:id/edit" element={<MetadataEditorRoute />} />
          </Routes>
        </ResourceDefinitionContextProvider>
      </AdminContext>
    </TestMemoryRouter>,
  );
};

describe("the full screen record editor", () => {
  beforeEach(() => {
    // jsdom has none and the jump-to-field effect calls it
    Element.prototype.scrollIntoView = vi.fn();
  });

  it("shows the profile sections and pre-validates the rules", async () => {
    setup();
    // the rail carries the profile's section, not a second overview
    expect(
      await screen.findByRole("heading", { name: "Identification" }),
    ).toBeInTheDocument();
    // the empty mandatory title is a finding before any save is attempted
    expect(await screen.findByText("A title is required.")).toBeInTheDocument();
    // and the rail badge counts it into the section
    expect(screen.getByText("metadataEditor.errorCount")).toBeInTheDocument();
  });

  it("shows only the profile fields until Advanced mode adds the others", async () => {
    setup();
    await screen.findByRole("heading", { name: "Identification" });
    expect(screen.queryByLabelText("lineStatement")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("metadataEditor.advanced"));
    await waitFor(() =>
      expect(screen.getByLabelText("lineStatement")).toBeInTheDocument(),
    );
    // unclaimed writable fields land in the "other" section the rail adds
    expect(screen.getByText("metadataEditor.otherElements")).toBeInTheDocument();
  });

  it("switches the pane to the reused read-only cards", async () => {
    setup();
    await screen.findByRole("heading", { name: "Identification" });
    fireEvent.click(screen.getByText("recordShow.contacts"));
    expect(await screen.findByText("Contacts card")).toBeInTheDocument();
    fireEvent.click(screen.getByText("recordShow.relations"));
    expect(await screen.findByText("Relations card")).toBeInTheDocument();
    // the changelog entry only exists because the schema knows the endpoint
    fireEvent.click(screen.getByText("recordShow.history"));
    expect(await screen.findByText("Changes card")).toBeInTheDocument();
  });

  it("refuses to edit a record the user may not edit", async () => {
    setup("DatasetMetadataRecord", makeRecord({ allowedActions: [] }));
    expect(
      await screen.findByText("metadataEditor.noPermission"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("metadataEditor.saveAndPublish"),
    ).not.toBeInTheDocument();
    // the read-only areas still answer
    fireEvent.click(screen.getByText("recordShow.contacts"));
    expect(await screen.findByText("Contacts card")).toBeInTheDocument();
  });

  it("answers a wrong record kind with the 404 page", async () => {
    setup("NotARecordKind");
    expect(
      await screen.findByText(/not found|ra\.page\.not_found/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("metadataEditor.sections"),
    ).not.toBeInTheDocument();
  });
});
