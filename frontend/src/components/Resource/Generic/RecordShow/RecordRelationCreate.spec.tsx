import type { RelationGroup } from "./RecordRelations";

import {
  AdminContext,
  ResourceDefinitionContextProvider,
  TestMemoryRouter,
  testDataProvider,
  type DataProvider,
} from "react-admin";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import i18nProvider from "../../../../providers/i18nProvider";
import RecordRelationCreate, {
  relationRow,
} from "./RecordRelationCreate";

// the partner picker asks the list of its kind through the schema layer, which
// is the subject of its own spec; here it stands for what the dialog hands it,
// stating the key and the sentence it was given as one text
vi.mock("../../../../jsonapi/components/SchemaAutocompleteInput", () => ({
  default: ({
    label,
    helperText,
  }: {
    label?: string;
    helperText?: string;
  }) => (
    <div>
      {`${String(label)}: ${String(helperText)}`}
    </div>
  ),
}));

const groups: RelationGroup[] = [
  {
    source: "layer",
    filter: "layer",
    resource: "Layer",
    kind: "element",
    edge: "describes Layer",
  },
  {
    source: "datasetMetadata",
    filter: "dataset_metadata",
    resource: "DatasetMetadataRecord",
    kind: "record",
    edge: "operates on DatasetMetadataRecord",
  },
];

const setup = () => {
  const getList = vi.fn();
  render(
    <TestMemoryRouter>
      <AdminContext
        i18nProvider={i18nProvider}
        dataProvider={testDataProvider({
          getList: getList as DataProvider["getList"],
        })}
      >
        <ResourceDefinitionContextProvider
          definitions={{
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
          <RecordRelationCreate
            ownColumn="serviceMetadata"
            record={{ id: "service-1", title: "Service metadata" }}
            groups={groups}
          />
        </ResourceDefinitionContextProvider>
      </AdminContext>
    </TestMemoryRouter>,
  );
  return getList;
};

describe("the row a declaration writes", () => {
  it("carries the partner in the member of the chosen kind", () => {
    // the member names of the api, the two choices of the curator and the
    // record the screen shows: that is the whole write body (#985)
    expect(
      relationRow({ kind: "layer", target: { id: "l-1" } }, "serviceMetadata", "s-1"),
    ).toEqual({ serviceMetadata: { id: "s-1" }, layer: { id: "l-1" } });
    expect(
      relationRow(
        { kind: "datasetMetadata", target: { id: "d-1" } },
        "serviceMetadata",
        "s-1",
      ),
    ).toEqual({ serviceMetadata: { id: "s-1" }, datasetMetadata: { id: "d-1" } });
  });

  it("sends neither the kind nor the partner as themselves", () => {
    // `kind` and `target` are the form's, no members of the schema: a body
    // which named them would ask the api for something it does not have
    const row = relationRow(
      { kind: "layer", target: { id: "l-1" }, origin: 4 },
      "datasetMetadata",
      "d-1",
    );
    expect(row).not.toHaveProperty("kind");
    expect(row).not.toHaveProperty("target");
    expect(row).toEqual({
      origin: 4,
      datasetMetadata: { id: "d-1" },
      layer: { id: "l-1" },
    });
  });

  it("writes nothing about a coupling it cannot name", () => {
    expect(relationRow({ target: null }, "serviceMetadata", "s-1")).toEqual({});
  });
});

describe("the dialog of a declaration", () => {
  it("asks nothing until the curator opens it", async () => {
    setup();
    // the partner picker asks a list of its kind as soon as it is mounted, so
    // the form exists only while the dialog is open
    expect(screen.queryByText(/recordShow\.partner/)).not.toBeInTheDocument();
    fireEvent.click(
      await screen.findByRole("button", { name: /declare a relation/i }),
    );
    expect(await screen.findByText(/recordShow\.partner/)).toBeInTheDocument();
  });

  it("keys the partner picker to the chosen kind", async () => {
    setup();
    fireEvent.click(
      await screen.findByRole("button", { name: /declare a relation/i }),
    );
    // the first offer of a service record is the layer it may describe, and the
    // picker names itself with the sentence of that group
    expect(
      await screen.findByText("recordShow.partner: describes Layer"),
    ).toBeInTheDocument();
    // the choice of the kind is what decides that sentence
    expect(screen.getByLabelText("Kind of relation")).toBeInTheDocument();
    expect(
      screen.getByText(/Service metadata is one end of the coupling/),
    ).toBeInTheDocument();
  });
});
