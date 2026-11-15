import {
  AdminContext,
  type DataProvider,
  RaRecord,
  ResourceContextProvider,
  TextInput,
  testDataProvider,
} from "react-admin";

import { fireEvent, render, screen, within } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";

import en from "../../../../i18n/en";
import { CreateMetadataRecord } from "./CreateMetadataRecord";

vi.mock("../../../../context/HttpClientContext", () => ({ useHttpClientContext: () => ({}) }));
vi.mock("../../../../jsonapi/hooks/useResourceSchema", () => ({ default: () => ({ operation: {} }) }));
vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: ({ operationId }: { operationId: string }) =>
    operationId === "create_DatasetMetadataRecord"
      ? [
        { component: TextInput, props: { source: "profile" } },
        { component: TextInput, props: { source: "title" } },
        { component: TextInput, props: { source: "abstract" } },
        // mandatory in the profile, but the schema answers it read-only
        { component: TextInput, props: { source: "metadataContact", disabled: true } },
        { component: TextInput, props: { source: "charset" } },
      ]
      : [],
}));

// trimmed mirror of the profile seeded by registry migration 0049
const SECTIONS = [
  {
    id: "identification",
    label: "Identification",
    fields: [
      { field: "title", requirement: "mandatory" },
      { field: "abstract", requirement: "mandatory" },
      { field: "metadataContact", requirement: "mandatory" },
    ],
  },
  {
    id: "extent",
    label: "Spatial and temporal extent",
    fields: [{ field: "boundingGeometry", requirement: "recommended" }],
  },
  {
    id: "quality",
    label: "Data quality",
    fields: [{ field: "charset", requirement: "mandatory" }],
  },
];

const renderScreen = (profiles: RaRecord[]) => render(
  <AdminContext
    dataProvider={testDataProvider({
      getList: (async () => ({ data: profiles, total: profiles.length })) as DataProvider["getList"],
    })}
    i18nProvider={polyglotI18nProvider(() => en, "en")}
  >
    <ResourceContextProvider value="DatasetMetadataRecord">
      <CreateMetadataRecord />
    </ResourceContextProvider>
  </AdminContext>,
);

describe("CreateMetadataRecord", () => {
  it("asks the mandatory fields of the chosen profile and shows the plan", async () => {
    renderScreen([{ id: "p1", sections: SECTIONS }]);

    expect(await screen.findByText("Start point")).toBeInTheDocument();
    // without a chosen profile the plan panel only explains the choice
    expect(screen.getByText(/profile decides which fields/)).toBeInTheDocument();

    // the profile selector and the mandatory fields render MUI's required
    // asterisk inside the label, so the matchers are prefixes
    fireEvent.change(screen.getByLabelText(/^Profile/), { target: { value: "p1" } });

    expect(screen.getByText("Created with content now:")).toBeInTheDocument();
    expect(screen.getByText("Identification")).toBeInTheDocument();
    expect(screen.getByText("Data quality")).toBeInTheDocument();
    expect(screen.getByText("Added later in Advanced mode:")).toBeInTheDocument();
    expect(screen.getByText("Spatial and temporal extent")).toBeInTheDocument();

    // the asked fields: the mandatory writable ones from the profile
    expect(screen.getByLabelText(/^Title/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Abstract/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Charset/)).toBeInTheDocument();
    // and nothing else from the schema: metadataContact is read-only here
    expect(screen.queryByText("Metadata Contact")).not.toBeInTheDocument();
  });

  it("offers the optional file identifier with its uniqueness promise", async () => {
    renderScreen([{ id: "p1", sections: SECTIONS }]);
    expect(await screen.findByLabelText("File identifier")).toBeInTheDocument();
    expect(screen.getByText(/Leave empty to get a generated UUID/)).toBeInTheDocument();
  });

  it("reserves the template step visibly instead of half-implementing it", async () => {
    renderScreen([{ id: "p1", sections: SECTIONS }]);
    expect(await screen.findByText("Template")).toBeInTheDocument();
    expect(screen.getByText("Blank record")).toBeInTheDocument();
    expect(screen.getByRole("radio")).toBeDisabled();
    expect(screen.getByText("Templates are coming later")).toBeInTheDocument();
  });

  it("names the editor marker and the identity promise", async () => {
    renderScreen([{ id: "p1", sections: SECTIONS }]);
    expect(await screen.findByText(/marked as saved by the editor/)).toBeInTheDocument();
    expect(screen.getByText(/must not exist yet/)).toBeInTheDocument();
  });

  it("says so when no profile can be loaded", async () => {
    renderScreen([]);
    expect(await screen.findByText(/No metadata profile could be loaded/)).toBeInTheDocument();
    expect(screen.queryByText("Start point")).not.toBeInTheDocument();
  });

  it("leaves sections without any asked field out of the created list", async () => {
    // a profile whose mandatory field is not writable asks nothing at all
    renderScreen([{
      id: "p2",
      sections: [{
        id: "only-contact",
        label: "Contacts",
        fields: [{ field: "metadataContact", requirement: "mandatory" }],
      }],
    }]);
    expect(await screen.findByText("Start point")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Profile/), { target: { value: "p2" } });
    // the section labels repeat between the two lists, so the assertions
    // scope to the list that names them
    const created = within(screen.getByText("Created with content now:").parentElement as HTMLElement);
    expect(created.queryByText("Contacts")).not.toBeInTheDocument();
    expect(screen.getByText("Added later in Advanced mode:")).toBeInTheDocument();
    const addedLater = within(screen.getByText("Added later in Advanced mode:").parentElement as HTMLElement);
    expect(addedLater.getByText("Contacts")).toBeInTheDocument();
  });
});
