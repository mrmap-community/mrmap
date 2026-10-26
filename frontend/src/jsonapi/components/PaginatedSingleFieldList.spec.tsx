import {
  AdminContext,
  ListContextProvider,
  ResourceContextProvider,
  ResourceDefinitionContextProvider,
  testDataProvider,
  useList,
} from "react-admin";

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PaginatedSingleFieldList } from "./PaginatedSingleFieldList";

// the dialog with its portal needs more than the default timeout
vi.setConfig({ testTimeout: 20000 });

const records = [1, 2, 3, 4, 5].map((id) => ({
  id,
  stringRepresentation: `Record ${id}`,
}));

const Harness = () => {
  const listContext = useList({ data: records });
  return (
    <ResourceDefinitionContextProvider
      definitions={{
        Keyword: {
          name: "Keyword",
          recordRepresentation: "stringRepresentation",
        },
      }}
    >
      <ResourceContextProvider value="Keyword">
        <ListContextProvider value={listContext}>
          <PaginatedSingleFieldList visibleCount={2} />
        </ListContextProvider>
      </ResourceContextProvider>
    </ResourceDefinitionContextProvider>
  );
};

const renderList = () =>
  render(
    <AdminContext dataProvider={testDataProvider()} i18nProvider={undefined}>
      <Harness />
    </AdminContext>,
  );

describe("PaginatedSingleFieldList", () => {
  it("shows only the visible chips and opens all records in a closable dialog", async () => {
    renderList();
    expect(screen.getByText("Record 1")).toBeInTheDocument();
    expect(screen.getByText("Record 2")).toBeInTheDocument();
    expect(screen.queryByText("Record 4")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+3 more" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAccessibleName("All related Keyword Records");
    expect(within(dialog).getAllByText(/Record \d/)).toHaveLength(5);
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });
});
