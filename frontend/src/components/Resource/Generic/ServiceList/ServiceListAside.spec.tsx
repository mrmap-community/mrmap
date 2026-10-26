import { AdminContext, ResourceContextProvider, TextField } from "react-admin";

import { fireEvent, render, screen } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { beforeEach, describe, expect, it, vi } from "vitest";

import en from "../../../../i18n/en";
import { SelectedRecordContextProvider, useSelectedRecordContext } from "../../../../jsonapi/components/SelectedRecordContext";
import ServiceListAside from "./ServiceListAside";

const state = vi.hoisted(() => ({ hasHistory: true }));
vi.mock("../../../../jsonapi/hooks/useOperation", () => ({
  default: () => state.hasHistory ? {} : undefined,
}));
vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: () => [{ component: TextField, props: { source: "title" } }],
}));
vi.mock("../History/HistoryList", () => ({
  default: ({ resource }: { resource?: string }) => (
    <div>Recent changes of {resource}</div>
  ),
}));
vi.mock("../ServiceShow/ServicePreviewImage", () => ({ default: () => <div>Service preview</div> }));
vi.mock("../ServiceShow/ActivateServiceButton", () => ({ default: () => <button>Activate service</button> }));
vi.mock("../../WebMapService/Button/MapViewerButton", () => ({ default: () => <button>Map viewer</button> }));
vi.mock("../ServiceShow/ServiceOutcomes", () => ({ default: () => <div>Outcomes of the service</div> }));

const Selection = () => {
  const { setSelectedRecord } = useSelectedRecordContext();
  return <>
    <button onClick={() => setSelectedRecord({ id: "service", title: "Selected WMS" })}>Select service</button>
    <button onClick={() => setSelectedRecord(undefined)}>Clear selection</button>
  </>;
};

const renderAside = (translated = false) => render(
  <AdminContext i18nProvider={translated ? polyglotI18nProvider(() => en, "en") : undefined}>
    <ResourceContextProvider value="WebMapService">
      <SelectedRecordContextProvider>
        <Selection />
        <ServiceListAside protocol="WMS" />
      </SelectedRecordContextProvider>
    </ResourceContextProvider>
  </AdminContext>,
);

describe("ServiceListAside", () => {
  beforeEach(() => { state.hasHistory = true; });

  it("shows a selection prompt without preview or actions until a service is selected", () => {
    renderAside();
    expect(screen.getByText("serviceList.noSelection")).toBeInTheDocument();
    expect(screen.queryByText("Service preview")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Map viewer" })).not.toBeInTheDocument();
    expect(screen.queryByText("Outcomes of the service")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Select service" }));
    expect(screen.getByText("Selected WMS")).toBeInTheDocument();
    expect(screen.getByText("Service preview")).toBeInTheDocument();
    expect(screen.getByText("Outcomes of the service")).toBeInTheDocument();
    expect(screen.queryByText("serviceList.noSelection")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(screen.getByText("serviceList.noSelection")).toBeInTheDocument();
    expect(screen.queryByText("Selected WMS")).not.toBeInTheDocument();
    expect(screen.queryByText("Outcomes of the service")).not.toBeInTheDocument();
  });

  it("answers the selected service above the recent changes of the resource", () => {
    renderAside();
    const changes = screen.getByText("Recent changes of HistoricalWebMapService");
    expect(
      changes.compareDocumentPosition(screen.getByText("serviceShow.details")) &
        Node.DOCUMENT_POSITION_PRECEDING,
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Select service" }));
    expect(changes).toHaveTextContent("HistoricalWebMapService");
  });

  it("does not request history when the resource has no history endpoint", () => {
    state.hasHistory = false;
    renderAside();
    expect(screen.queryByText(/Recent changes of/)).not.toBeInTheDocument();
    expect(screen.getByText("serviceList.noSelection")).toBeInTheDocument();
  });

  it("offers exactly one way to the service which is selected after another", () => {
    const SelectTwo = () => {
      const { setSelectedRecord } = useSelectedRecordContext();
      return <>
        <button onClick={() => setSelectedRecord({ id: "a", title: "First WMS" })}>Select first</button>
        <button onClick={() => setSelectedRecord({ id: "b", title: "Second WMS" })}>Select second</button>
      </>;
    };
    render(
      <AdminContext i18nProvider={polyglotI18nProvider(() => en, "en")}>
        <ResourceContextProvider value="WebMapService">
          <SelectedRecordContextProvider>
            <SelectTwo />
            <ServiceListAside protocol="WMS" />
          </SelectedRecordContextProvider>
        </ResourceContextProvider>
      </AdminContext>,
    );
    // the footer of the card of a WMS holds the way to the details and the way
    // to the map viewer: a way to the details which is mounted anew under the
    // same key as the way to the map viewer leaves a button of every selection
    // before behind
    fireEvent.click(screen.getByRole("button", { name: "Select first" }));
    expect(screen.getAllByRole("link", { name: "Open details" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Select second" }));
    const ways = screen.getAllByRole("link", { name: "Open details" });
    expect(ways).toHaveLength(1);
    expect(ways[0]).toHaveAttribute("href", "#/WebMapService/b/show");
  });

  it("explains the changelog scope using the service title", () => {
    renderAside(true);
    expect(screen.getByText("Recent changes")).toBeInTheDocument();
    expect(screen.getByText("Latest 10 changes across all services")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Select service" }));
    expect(screen.getByText("Recent changes")).toBeInTheDocument();
    expect(screen.getByText("Latest 10 changes to Selected WMS")).toBeInTheDocument();
    expect(screen.queryByText("Latest 10 changes across all services")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(screen.getByText("Latest 10 changes across all services")).toBeInTheDocument();
  });
});
