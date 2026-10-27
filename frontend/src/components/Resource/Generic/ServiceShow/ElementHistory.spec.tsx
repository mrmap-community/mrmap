import { AdminContext, testDataProvider } from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ElementHistory from "./ElementHistory";

const state = vi.hoisted(() => ({
  operations: [] as string[],
}));

/** The operation which lists the history of a resource exists only for some. */
vi.mock("../../../../jsonapi/hooks/useOperation", () => ({
  default: (name: string) =>
    state.operations.includes(name) ? { name, type: "list" } : undefined,
}));

// the feed of the changelog scopes itself to the record which is selected, so the
// mock answers with the record the element history named to that context
vi.mock("../History/HistoryList", async () => {
  const { useSelectedRecordContext } = await import(
    "../../../../jsonapi/components/SelectedRecordContext"
  );
  return {
    default: () => {
      const { selectedRecord } = useSelectedRecordContext();
      return <span>events of {String(selectedRecord?.id)}</span>;
    },
  };
});

const showHistory = (resource: string, record?: { id: string; title?: string }) =>
  render(
    <AdminContext dataProvider={testDataProvider()}>
      <ElementHistory resource={resource} record={record} />
    </AdminContext>,
  );

describe("element history", () => {
  it("is absent when the history of the element can not be listed", () => {
    state.operations = [];
    showHistory("Layer", { id: "layer-1" });
    expect(screen.queryByText("events of layer-1")).not.toBeInTheDocument();
  });

  it("is absent for an element which has no identifier", () => {
    state.operations = ["list_HistoricalLayer"];
    showHistory("Layer");
    expect(screen.queryByText(/^events of/)).not.toBeInTheDocument();
  });

  it("shows the events of the element which is inspected", () => {
    state.operations = ["list_HistoricalLayer"];
    showHistory("Layer", { id: "layer-1", title: "roads" });
    expect(screen.getByText("events of layer-1")).toBeInTheDocument();
  });

  it("names the element whose events are shown", () => {
    state.operations = ["list_HistoricalFeatureType"];
    showHistory("FeatureType", { id: "featuretype-1", title: "buildings" });
    expect(screen.getByText("historyList.title")).toBeInTheDocument();
    expect(screen.getByText("historyList.selectedElement")).toBeInTheDocument();
  });
});