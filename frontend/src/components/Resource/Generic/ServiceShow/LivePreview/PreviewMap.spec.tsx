import type { FeatureCollection } from "geojson";

import { type PropsWithChildren } from "react";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PreviewMap, { validExtent } from "./PreviewMap";

const state = vi.hoisted(() => ({
  fit: vi.fn(),
  click: undefined as (() => void) | undefined,
  image: vi.fn(),
}));
vi.mock("react-admin", () => ({ useTranslate: () => (key: string) => key }));
vi.mock("../../../../MapContainer/ResizeAbleMapContainer", () => ({
  default: () => null,
}));
vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: PropsWithChildren) => <div>{children}</div>,
  useMap: () => ({
    fitBounds: state.fit,
    getBounds: () => ({
      getWest: () => 0,
      getEast: () => 4,
      getSouth: () => 0,
      getNorth: () => 8,
    }),
    getSize: () => ({ x: 600, y: 400 }),
  }),
  useMapEvents: () => ({}),
  ImageOverlay: (props: object) => {
    state.image(props);
    return null;
  },
  Rectangle: () => <span>metadata extent</span>,
  GeoJSON: ({
    data,
    onEachFeature,
  }: {
    data: FeatureCollection;
    onEachFeature: (feature: object, layer: object) => void;
  }) => {
    data.features.forEach((feature) =>
      onEachFeature(feature, {
        on: (event: string, callback: () => void) => {
          if (event === "click") state.click = callback;
        },
      }),
    );
    return <button onClick={() => state.click?.()}>Select feature</button>;
  },
}));
beforeEach(() => {
  vi.clearAllMocks();
  state.click = undefined;
});
describe("preview geometry and viewport", () => {
  it("accepts zero-degree coordinates, and rejects invalid, reversed or degenerate extents", () => {
    expect(validExtent([0, -2, 4, 0])).toBe(true);
    for (const value of [
      null,
      [0, 0, 0, 0],
      [4, 0, 0, 8],
      [0, 0, 4, Infinity],
      [-200, 0, 4, 8],
    ])
      expect(validExtent(value)).toBe(false);
  });
  it("fits the selected metadata extent and labels current-page coverage", () => {
    render(
      <PreviewMap
        records={[{ identifier: "r", extent: [0, -2, 4, 0], previews: [] }]}
        extent={[0, -2, 4, 0]}
        onViewport={() => {}}
      />,
    );
    expect(state.fit).toHaveBeenCalled();
    expect(screen.getByText("livePreview.coverage")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "livePreview.zoom" }));
    expect(state.fit.mock.calls.length).toBeGreaterThan(1);
  });
  it("keeps missing extents usable and safely displays feature attributes as text", () => {
    render(
      <PreviewMap
        onViewport={() => {}}
        features={{
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              properties: { unsafe: "<img src=x onerror=alert(1)>" },
              geometry: { type: "Point", coordinates: [0, 0] },
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("livePreview.noExtent")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Select feature" }));
    expect(
      screen.getByText("unsafe: <img src=x onerror=alert(1)>"),
    ).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
