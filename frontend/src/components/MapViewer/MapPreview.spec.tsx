import type { PropsWithChildren } from "react";
import { act } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase";
import MapPreview from "./MapPreview";
import { MapViewerBase, useMapViewerBase } from "./MapViewerBase";

const captured = vi.hoisted(() => ({ props: undefined as Record<string, unknown> | undefined }));

const fakeMap = {
  getCenter: () => ({ lat: 51.505, lng: -0.09 }),
  getBounds: () => ({
    getSouthWest: () => ({ lat: 49, lng: 6 }),
    getNorthEast: () => ({ lat: 55, lng: 12 }),
    getWest: () => 6,
    getSouth: () => 49,
    getEast: () => 12,
    getNorth: () => 55,
  }),
  getSize: () => ({ x: 400, y: 300 }),
  getZoom: () => 6,
  getContainer: () => document.createElement("div"),
  getPane: () => undefined,
  createPane: () => document.createElement("div"),
  invalidateSize: () => undefined,
  on: () => undefined,
  off: () => undefined,
  fitBounds: () => undefined,
};

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children, ...rest }: PropsWithChildren<Record<string, unknown>>) => {
    captured.props = rest;
    return <div data-testid="map">{children}</div>;
  },
  ScaleControl: () => <span data-testid="scale" />,
}));
vi.mock("../MapContainer/GetMapControl", () => ({ default: () => <div data-testid="map-control" /> }));
vi.mock("../MapContainer/GetFeatureControl", () => ({
  default: () => <div data-testid="feature-control" />,
}));
vi.mock("../MapContainer/ResizeAbleMapContainer", () => ({ default: () => null }));

/** Names whether the map reached the state the viewer's controls work on. */
const MapState = () => <span>{useMapViewerBase().map === undefined ? "no map" : "map handed over"}</span>;

const renderPreview = (props: PropsWithChildren<{ height?: number | string }> = {}) =>
  render(
    <OwsContextBase>
      <MapViewerBase>
        <MapPreview {...props} />
        <MapState />
      </MapViewerBase>
    </OwsContextBase>,
  );

describe("the map of the viewer without its screens", () => {
  it("renders one map with the controls which ask the document for its view", () => {
    renderPreview();

    expect(screen.getAllByTestId("map")).toHaveLength(1);
    expect(screen.getByTestId("map-control")).toBeInTheDocument();
    expect(screen.getByTestId("feature-control")).toBeInTheDocument();
    expect(screen.getByTestId("scale")).toBeInTheDocument();
  });

  it("leaves the layer tree, the drawers and the tabs of the full viewer beside it", () => {
    renderPreview();

    expect(screen.queryByRole("tree")).toBeNull();
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.queryByRole("tabpanel")).toBeNull();
  });

  it("keeps the coordinate reference system and the zoom limits of the viewer", () => {
    renderPreview();

    const props = captured.props as Record<string, never>;
    expect((props.crs as { code: string }).code).toBe("EPSG:4326");
    expect(props.zoom).toBe(2);
    expect(props.minZoom).toBe(0);
    expect(props.maxZoom).toBe(20);
    expect(props.maxBoundsViscosity).toBe(0.8);
    expect(props.scrollWheelZoom).toBe(true);
  });

  it("hands the map to the viewer base, which is what its controls ask", () => {
    renderPreview();
    expect(screen.getByText("no map")).toBeInTheDocument();

    const ref = (captured.props as Record<string, (map: unknown) => void>).ref;
    act(() => ref(fakeMap));

    expect(screen.getByText("map handed over")).toBeInTheDocument();
  });

  it("sizes itself to the space the preview asks for", () => {
    renderPreview({ height: 240 });

    expect(screen.getByTestId("map").parentElement).toHaveStyle({ height: "240px" });
  });
});
