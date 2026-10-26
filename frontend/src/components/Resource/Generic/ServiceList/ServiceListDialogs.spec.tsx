import { AdminContext, CreateButton, EditButton, ResourceContextProvider, ResourceDefinitionContextProvider, memoryStore, testDataProvider } from "react-admin";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";

import en from "../../../../i18n/en";
import CatalogueServiceList from "../../CatalogueService/CatalogueServiceList";
import ListWebFeatureService from "../../WebFeatureService/List/ListWebFeatureService";
import ListWebMapService from "../../WebMapService/List/ListWebMapService";

// Keep the real resource screens, routing, forms and dialogs; isolate list data and schema loading.
vi.mock("../../../../jsonapi/components/ListGuesser", () => ({
  default: () => {
    const location = useLocation();
    return <>
      <output aria-label="Location">{location.pathname}</output>
      <CreateButton />
      <EditButton record={{ id: "service-1" }} />
    </>;
  },
}));
vi.mock("../../../../jsonapi/components/SchemaFormFields", () => ({
  default: () => <p>Service form fields</p>,
}));

vi.mock("../../../../jsonapi/hooks/useResourceSchema", () => ({ default: () => ({}) }));
vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({ useFieldsForOperation: () => [] }));

const cases = [
  { resource: "WebMapService", List: ListWebMapService },
  { resource: "WebFeatureService", List: ListWebFeatureService },
  { resource: "CatalogueService", List: CatalogueServiceList },
];

const renderList = (resource: string, List: typeof CatalogueServiceList, path = `/${resource}`) => render(
  <MemoryRouter initialEntries={[path]}>
    <AdminContext i18nProvider={polyglotI18nProvider(() => en, "en")} store={memoryStore()} dataProvider={testDataProvider({
      getOne: vi.fn().mockResolvedValue({ data: { id: "service-1" } }),
    })}>
      <ResourceDefinitionContextProvider definitions={{
        [resource]: { name: resource, hasList: true, hasCreate: true, hasEdit: true, hasShow: true, options: { label: resource } },
      }}>
        <ResourceContextProvider value={resource}>
          <Routes>
            <Route path={`/${resource}/*`} element={<List />} />
          </Routes>
        </ResourceContextProvider>
      </ResourceDefinitionContextProvider>
    </AdminContext>
  </MemoryRouter>,
);

describe.each(cases)("$resource list dialogs", ({ resource, List }) => {
  it("opens Create from the list and closes back to the list", async () => {
    renderList(resource, List);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Create" }));
    expect(screen.getByLabelText("Location")).toHaveTextContent(`/${resource}/create`);
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(`Create ${resource}`);
    expect(dialog).toHaveTextContent("Service form fields");
    fireEvent.click(dialog.querySelector("button")!);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByLabelText("Location")).toHaveTextContent(`/${resource}`);
  });

  it("opens the create dialog when loading its URL directly", async () => {
    renderList(resource, List, `/${resource}/create`);
    expect(await screen.findByRole("dialog")).toHaveTextContent(`Create ${resource}`);
  });

  it("opens the edit dialog from the list", async () => {
    renderList(resource, List);
    fireEvent.click(screen.getByRole("link", { name: "Edit" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent("Edit");
    expect(screen.getByLabelText("Location")).toHaveTextContent(`/${resource}/service-1`);
  });

  it("closes the create dialog with the labelled close control back to the list", async () => {
    renderList(resource, List, `/${resource}/create`);
    expect(await screen.findByRole("dialog")).toHaveTextContent(`Create ${resource}`);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByLabelText("Location")).toHaveTextContent(`/${resource}`);
  });
});
