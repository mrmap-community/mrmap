import { useEffect } from "react";
import type { DataProvider } from "react-admin";
import { useReferenceManyErrors } from "../../../../jsonapi/components/ReferenceManyErrorsProvider";
import Records from "../../CatalogueService/Show/Records";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  AdminContext,
  EditButton,
  ResourceContextProvider,
  ResourceDefinitionContextProvider,
  Show,
  TestMemoryRouter,
  TextInput,
  testDataProvider,
  useRecordContext,
  useResourceContext,
} from "react-admin";
import { Route, Routes, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SchemaAutocompleteInput from "../../../../jsonapi/components/SchemaAutocompleteInput";
import ConfigureRelatedResource from "../../../../jsonapi/components/ConfigureRelatedResource";
import ServiceShow, { type ServiceTab } from "./ServiceShow";
import ServiceMetadataTab from "./ServiceMetadataTab";
import ServiceRelatedTab from "./ServiceRelatedTab";
import { capabilitiesUrl } from "./ServiceDetailsCard";

const state = vi.hoisted(() => ({
  operations: new Set<string>(),
  includes: ["operationUrls"],
  relationshipErrors: false,
}));
vi.mock("../../../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({
    api: {
      getOperation: (id: string) => (state.operations.has(id) ? {} : undefined),
    },
  }),
}));
vi.mock("../../../../jsonapi/hooks/useResourceSchema", () => ({
  default: () => ({ includeAbleResources: state.includes }),
}));
vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: ({ operationId }: { operationId: string }) => [
    { component: TextInput, props: { source: "title" } },
    {
      component: SchemaAutocompleteInput,
      props: {
        source: operationId.includes("Proxy") ? "securedService" : "service",
        reference: "CatalogueService",
      },
    },
  ],
}));
vi.mock("../../../../jsonapi/components/SchemaFormFields", () => ({
  default: () => {
    const { addErrors } = useReferenceManyErrors();
    useEffect(() => {
      if (state.relationshipErrors)
        addErrors([
          {
            source: "relations",
            index: 0,
            record: { id: "failed" },
            errors: { title: { message: "Invalid relation" } },
          },
        ]);
    }, [addErrors]);
    return <TextInput source="title" label="Title" />;
  },
}));
vi.mock("../../../../jsonapi/components/ListGuesser", () => ({
  default: ({
    relatedResource,
  }: {
    relatedResource: { resource: string; id: string };
  }) => {
    const resource = useResourceContext();
    return (
      <div>
        List {resource} for {relatedResource.resource}/{relatedResource.id}
        <EditButton record={{ id: "setting-1" }} />
      </div>
    );
  },
}));

const definitions = {
  CatalogueService: {
    name: "CatalogueService",
    hasShow: true,
    hasEdit: true,
    options: {},
  },
  HarvestingJob: {
    name: "HarvestingJob",
    hasList: true,
    hasEdit: true,
    hasCreate: true,
    options: {},
  },
  DatasetMetadataRecord: {
    name: "DatasetMetadataRecord",
    hasList: true,
    hasEdit: true,
    options: {},
  },
  ServiceMetadataRecord: {
    name: "ServiceMetadataRecord",
    hasList: true,
    hasEdit: true,
    options: {},
  },
  CatalogueProxy: {
    name: "CatalogueProxy",
    hasList: true,
    hasEdit: true,
    hasCreate: true,
    options: {},
  },
};
function RecordTitle() {
  const record = useRecordContext();
  return <div>Overview {record?.title}</div>;
}
const getOne = vi.fn(async (resource: string, { id }: { id: string }) => ({
  data: {
    id,
    title: resource === "CatalogueService" ? "Catalogue" : "Setting",
  },
}));
const update = vi.fn(
  async (_resource: string, { id, data }: { id: string; data: object }) => ({
    data: { id, ...data },
  }),
);
const create = vi.fn(async (_resource: string, { data }: { data: object }) => ({
  data: { id: "new-setting", ...data },
}));
const getList = vi.fn(async () => ({ data: [], total: 0 }));
function setup(path: string, tabs: ServiceTab[]) {
  return render(
    <TestMemoryRouter initialEntries={[path]}>
      <AdminContext
        dataProvider={testDataProvider({
          getOne: getOne as DataProvider["getOne"],
          update: update as DataProvider["update"],
          create: create as DataProvider["create"],
          getList,
        })}
      >
        <ResourceDefinitionContextProvider definitions={definitions}>
          <ResourceContextProvider value="CatalogueService">
            <Routes>
              <Route
                path="/CatalogueService/:id/show/*"
                element={<ServiceShow tabs={tabs} />}
              />
            </Routes>
          </ResourceContextProvider>
        </ResourceDefinitionContextProvider>
      </AdminContext>
    </TestMemoryRouter>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  state.relationshipErrors = false;
  state.operations = new Set([
    "partial_update_CatalogueService",
    "create_CatalogueProxy",
    "partial_update_CatalogueProxy",
  ]);
  state.includes = ["operationUrls"];
});

describe("shared service show", () => {
  it("gates tabs by schema and preserves deep dialog navigation and parent scope", async () => {
    setup("/CatalogueService/csw-1/show/HarvestingJob/setting-1", [
      { path: "", label: "Overview", content: <RecordTitle /> },
      {
        path: "unsupported",
        label: "Unavailable",
        operation: "absent",
        content: <div>Unavailable</div>,
      },
      {
        path: "HarvestingJob/*",
        label: "Harvesting",
        content: <ServiceRelatedTab resource="HarvestingJob" />,
      },
    ]);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Harvesting", hidden: true }),
    ).toHaveAttribute("aria-selected", "true");
    expect(
      screen.queryByRole("tab", { name: "Unavailable" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("List HarvestingJob for CatalogueService/csw-1"),
    ).toBeInTheDocument();
    expect(getOne).toHaveBeenCalledWith(
      "CatalogueService",
      expect.objectContaining({
        id: "csw-1",
        meta: { jsonApiParams: { include: "operationUrls" } },
      }),
    );
    expect(getOne).toHaveBeenCalledWith(
      "HarvestingJob",
      expect.objectContaining({ id: "setting-1" }),
    );
    fireEvent.change(await screen.findByRole("textbox", { name: "Title" }), {
      target: { value: "Edited" },
    });
    fireEvent.click(screen.getByRole("button", { name: "ra.action.save" }));
    await waitFor(() => expect(update).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("tab", { name: "Harvesting", hidden: true }),
    ).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
    expect(await screen.findByText("Overview Catalogue")).toBeInTheDocument();
  });
  it("saves metadata for the service ID and stays on its tab", async () => {
    state.includes = [];
    setup("/CatalogueService/csw-2/show/metadata", [
      { path: "", label: "Overview", content: <RecordTitle /> },
      { path: "metadata", label: "Metadata", content: <ServiceMetadataTab /> },
    ]);
    fireEvent.change(await screen.findByRole("textbox", { name: "Title" }), {
      target: { value: "Updated catalogue" },
    });
    fireEvent.click(screen.getByRole("button", { name: "ra.action.save" }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        "CatalogueService",
        expect.objectContaining({
          id: "csw-2",
          data: expect.objectContaining({ title: "Updated catalogue" }),
        }),
      ),
    );
    expect(screen.getByRole("tab", { name: "Metadata" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(getOne).toHaveBeenCalledWith(
      "CatalogueService",
      expect.objectContaining({ meta: { jsonApiParams: {} } }),
    );
  });
  it("creates related configuration with the current parent relationship", async () => {
    setup("/CatalogueService/csw-3/show/HarvestingJob/create", [
      { path: "", label: "Overview", content: <RecordTitle /> },
      {
        path: "HarvestingJob/*",
        label: "Harvesting",
        content: <ServiceRelatedTab resource="HarvestingJob" />,
      },
    ]);
    fireEvent.change(await screen.findByRole("textbox", { name: "Title" }), {
      target: { value: "New job" },
    });
    fireEvent.click(screen.getByRole("button", { name: "ra.action.save" }));
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith(
        "HarvestingJob",
        expect.objectContaining({
          data: expect.objectContaining({
            service: expect.objectContaining({ id: "csw-3" }),
            title: "New job",
          }),
        }),
      ),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });
});
it("keeps the related dialog open when relationship updates partially fail", async () => {
  state.relationshipErrors = true;
  setup("/CatalogueService/csw-1/show/HarvestingJob/setting-1", [
    { path: "", label: "Overview", content: <RecordTitle /> },
    {
      path: "HarvestingJob/*",
      label: "Harvesting",
      content: <ServiceRelatedTab resource="HarvestingJob" />,
    },
  ]);
  fireEvent.change(await screen.findByRole("textbox", { name: "Title" }), {
    target: { value: "Edited" },
  });
  fireEvent.click(screen.getByRole("button", { name: "ra.action.save" }));
  await waitFor(() => expect(update).toHaveBeenCalled());
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

it("opens only the selected CSW record list dialog", async () => {
  state.operations.add(
    "list_related_DatasetMetadataRecord_of_CatalogueService",
  );
  state.operations.add(
    "list_related_ServiceMetadataRecord_of_CatalogueService",
  );
  setup(
    "/CatalogueService/csw-1/show/records/DatasetMetadataRecord/setting-1",
    [
      { path: "", label: "Overview", content: <RecordTitle /> },
      { path: "records/*", label: "Records", content: <Records /> },
    ],
  );
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  expect(getOne).toHaveBeenCalledWith(
    "DatasetMetadataRecord",
    expect.objectContaining({ id: "setting-1" }),
  );
  expect(getOne).not.toHaveBeenCalledWith(
    "ServiceMetadataRecord",
    expect.anything(),
  );
});

function ProxyPage() {
  const navigate = useNavigate();
  return (
    <>
      <button onClick={() => navigate("/CatalogueService/second/show")}>
        Other service
      </button>
      <Show actions={false}>
        <ConfigureRelatedResource relatedResource="CatalogueProxy" />
      </Show>
    </>
  );
}
it("rebinds proxy defaults and the related query when navigating to another service", async () => {
  render(
    <TestMemoryRouter initialEntries={["/CatalogueService/first/show"]}>
      <AdminContext
        dataProvider={testDataProvider({
          getOne: getOne as DataProvider["getOne"],
          getList,
          create: create as DataProvider["create"],
        })}
      >
        <ResourceDefinitionContextProvider definitions={definitions}>
          <ResourceContextProvider value="CatalogueService">
            <Routes>
              <Route
                path="/CatalogueService/:id/show/*"
                element={<ProxyPage />}
              />
            </Routes>
          </ResourceContextProvider>
        </ResourceDefinitionContextProvider>
      </AdminContext>
    </TestMemoryRouter>,
  );
  await screen.findByRole("textbox", { name: "Title" });
  fireEvent.click(screen.getByRole("button", { name: "Other service" }));
  await waitFor(() =>
    expect(getList).toHaveBeenCalledWith(
      "CatalogueProxy",
      expect.objectContaining({
        meta: {
          relatedResource: { resource: "CatalogueService", id: "second" },
        },
      }),
    ),
  );
  fireEvent.change(await screen.findByRole("textbox", { name: "Title" }), {
    target: { value: "Proxy" },
  });
  fireEvent.click(screen.getByRole("button", { name: "ra.action.save" }));
  await waitFor(() =>
    expect(create).toHaveBeenCalledWith(
      "CatalogueProxy",
      expect.objectContaining({
        data: expect.objectContaining({
          securedService: expect.objectContaining({ id: "second" }),
        }),
      }),
    ),
  );
});
describe("capabilities links", () => {
  it.each(["WMS", "WFS", "CSW"] as const)(
    "builds a %s URL without mutating the API record",
    (protocol) => {
      const endpoint = Object.freeze({
        operation: 1,
        method: 1,
        url: "https://example.com/ows?token=abc",
      });
      const url = new URL(
        capabilitiesUrl({ operationUrls: [endpoint] }, protocol, "2.0.2")!,
      );
      expect(url.searchParams.get("SERVICE")).toBe(protocol);
      expect(url.searchParams.get("VERSION")).toBe("2.0.2");
      expect(url.searchParams.get("token")).toBe("abc");
      expect(endpoint.url).toBe("https://example.com/ows?token=abc");
    },
  );
  it("handles missing and malformed endpoints", () => {
    expect(capabilitiesUrl(undefined, "WMS")).toBeUndefined();
    expect(
      capabilitiesUrl(
        { operationUrls: [{ operation: 1, method: 1, url: "invalid" }] },
        "CSW",
      ),
    ).toBeUndefined();
  });
});
