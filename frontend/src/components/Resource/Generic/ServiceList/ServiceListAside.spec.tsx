import { fireEvent, render, screen } from "@testing-library/react";
import { AdminContext, ResourceContextProvider, TextField } from "react-admin";
import { beforeEach, describe, expect, it, vi } from "vitest";
import polyglotI18nProvider from "ra-i18n-polyglot";
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
vi.mock("../../../HistoryList", () => ({
  default: ({ resource, record }: { resource: string; record?: { id: string } }) => (
    <div>Last 10 events: {resource} {record?.id ?? "all services"}</div>
  ),
}));
vi.mock("../ServiceShow/ServicePreviewImage", () => ({ default: () => <div>Service preview</div> }));
vi.mock("../ServiceShow/ActivateServiceButton", () => ({ default: () => <button>Activate service</button> }));
vi.mock("../../WebMapService/Button/MapViewerButton", () => ({ default: () => <button>Map viewer</button> }));

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

    fireEvent.click(screen.getByRole("button", { name: "Select service" }));
    expect(screen.getByText("Selected WMS")).toBeInTheDocument();
    expect(screen.getByText("Service preview")).toBeInTheDocument();
    expect(screen.queryByText("serviceList.noSelection")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Clear selection" }));
    expect(screen.getByText("serviceList.noSelection")).toBeInTheDocument();
    expect(screen.queryByText("Selected WMS")).not.toBeInTheDocument();
  });

  it("keeps resource-wide events above the details when selection changes", () => {
    renderAside();
    const events = screen.getByText("Last 10 events: HistoricalWebMapService all services");
    expect(events.compareDocumentPosition(screen.getByText("serviceShow.details")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Select service" }));
    expect(events).toHaveTextContent("all services");
  });

  it("does not request history when the resource has no history endpoint", () => {
    state.hasHistory = false;
    renderAside();
    expect(screen.queryByText(/Last 10 events/)).not.toBeInTheDocument();
    expect(screen.getByText("serviceList.noSelection")).toBeInTheDocument();
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
