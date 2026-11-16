import type { ReactNode } from "react";
import {
  AdminContext,
  ListContextProvider,
  ResourceContextProvider,
} from "react-admin";

import { fireEvent, render, screen } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "../../../../i18n/en";
import { ExplorerView } from "./ExplorerView";

const state = vi.hoisted(() => ({
  onToggleItem: vi.fn(),
}));

const records = [
  { id: "r1", title: "First", abstract: "a", dateStamp: "2026-01-01" },
  { id: "r2", title: "Second", abstract: "b", dateStamp: "2026-01-02" },
];

// a list controller stand-in: ExplorerView only reads data, the selection
// state and the toggle callback out of the list context
const listContext = (selectedIds: string[]) =>
  ({
    data: records,
    total: records.length,
    isPending: false,
    sort: { field: "title", order: "ASC" },
    selectedIds,
    onToggleItem: state.onToggleItem,
    onSelectAll: vi.fn(),
  }) as never;

const view = (bulkActions?: ReactNode, selectedIds: string[] = []) => (
  <AdminContext i18nProvider={polyglotI18nProvider(() => en, "en")}>
    <ResourceContextProvider value="DatasetMetadataRecord">
      <ListContextProvider value={listContext(selectedIds)}>
        <ExplorerView
          MapComponent={() => null}
          rowActions={() => null}
          bulkActions={bulkActions}
        />
      </ListContextProvider>
    </ResourceContextProvider>
  </AdminContext>
);

const renderView = (bulkActions?: ReactNode, selectedIds?: string[]) =>
  render(view(bulkActions, selectedIds));

beforeEach(() => {
  state.onToggleItem.mockReset();
});

describe("explorer selection", () => {
  it("offers a selection checkbox per result when the screen has bulk actions", () => {
    renderView(<span>batch edit</span>);
    const checkboxes = screen.getAllByRole("checkbox", {
      name: "Select this record",
    });
    expect(checkboxes).toHaveLength(records.length);
    fireEvent.click(checkboxes[1]);
    expect(state.onToggleItem).toHaveBeenCalledWith("r2");
  });

  it("shows the bulk actions toolbar only for a non-empty selection", () => {
    const { rerender } = renderView(<span>batch edit</span>);
    expect(screen.queryByText("batch edit")).not.toBeInTheDocument();
    rerender(view(<span>batch edit</span>, ["r1"]));
    expect(screen.getByText("batch edit")).toBeInTheDocument();
    const checkboxes = screen.getAllByRole("checkbox", {
      name: "Select this record",
    });
    expect(checkboxes[0]).toBeChecked();
    expect(checkboxes[1]).not.toBeChecked();
  });

  it("keeps the plain result list without bulk actions", () => {
    renderView();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("First")).toBeInTheDocument();
  });
});
