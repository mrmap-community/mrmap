import type { RaRecord } from "react-admin";
import { ResourceContextProvider, useRecordContext } from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SelectedRecordContextProvider } from "../../../../jsonapi/components/SelectedRecordContext";
import SelectedElementViewerCard from "./SelectedElementViewerCard";

const { getOne } = vi.hoisted(() => ({ getOne: vi.fn() }));

vi.mock("react-admin", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-admin")>()),
  useGetOne: (resource: string, params: unknown, options: unknown) => getOne(resource, params, options),
}));

// the buttons of a service read their service from the record context, which is what the card under
// test has to hand them beside the element it was asked for
vi.mock("../../WebMapService/Button/ListActions", () => ({
  default: ({ element, size }: { element?: RaRecord; size?: string }) => (
    <span>
      wms buttons of {String(useRecordContext<RaRecord>()?.id)} for {String(element?.id)} in{" "}
      {String(size)}
    </span>
  ),
}));

vi.mock("../../WebFeatureService/Button/ListActions", () => ({
  default: ({ element }: { element?: RaRecord }) => (
    <span>wfs buttons of {String(useRecordContext<RaRecord>()?.id)} for {String(element?.id)}</span>
  ),
}));

const service = { id: "service-1", title: "Streets" };

const renderCard = (resource: string, selectedRecord?: RaRecord) =>
  render(
    <ResourceContextProvider value={resource}>
      <SelectedRecordContextProvider record={selectedRecord}>
        <SelectedElementViewerCard />
      </SelectedRecordContextProvider>
    </ResourceContextProvider>,
  );

describe("the map viewer button of the selected element", () => {
  it("asks the service which owns the selected layer", () => {
    getOne.mockReturnValue({ data: service, isPending: false, error: undefined });
    renderCard("Layer", { id: "layer-1", service: { id: "service-1" } });

    expect(getOne).toHaveBeenCalledWith(
      "WebMapService",
      { id: "service-1" },
      { enabled: true },
    );
    expect(screen.getByText("wms buttons of service-1 for layer-1 in small")).toBeInTheDocument();
  });

  it("asks the service which owns the selected feature type", () => {
    getOne.mockReturnValue({ data: service, isPending: false, error: undefined });
    renderCard("FeatureType", { id: "type-1", service: { id: "service-1" } });

    expect(getOne).toHaveBeenCalledWith(
      "WebFeatureService",
      { id: "service-1" },
      { enabled: true },
    );
    expect(screen.getByText("wfs buttons of service-1 for type-1")).toBeInTheDocument();
  });

  it("waits for the click of the list while nothing is selected", () => {
    getOne.mockReturnValue({ data: undefined, isPending: false, error: undefined });
    renderCard("Layer");

    expect(screen.getByText("layerInspection.select")).toBeInTheDocument();
    expect(getOne).toHaveBeenCalledWith("WebMapService", { id: undefined }, { enabled: false });
    expect(screen.queryByText(/buttons of/)).toBeNull();
  });

  it("asks nothing of a row which names no service", () => {
    getOne.mockReturnValue({ data: undefined, isPending: false, error: undefined });
    renderCard("Layer", { id: "layer-1" });

    expect(getOne).toHaveBeenCalledWith("WebMapService", { id: undefined }, { enabled: false });
    expect(screen.queryByText(/buttons of/)).toBeNull();
  });

  it("keeps the service it reads while it is asked", () => {
    getOne.mockReturnValue({ data: undefined, isPending: true, error: undefined });
    renderCard("Layer", { id: "layer-1", service: { id: "service-1" } });

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.queryByText(/buttons of/)).toBeNull();
  });

  it("says that the service could not be asked", () => {
    getOne.mockReturnValue({
      data: undefined,
      isPending: false,
      error: new Error("unreachable"),
    });
    renderCard("Layer", { id: "layer-1", service: { id: "service-1" } });

    expect(screen.getByText("ra.notification.http_error")).toBeInTheDocument();
    expect(screen.queryByText(/buttons of/)).toBeNull();
  });
});
