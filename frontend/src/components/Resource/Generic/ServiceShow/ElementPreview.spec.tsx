import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ElementPreview from "./ElementPreview";

const state = vi.hoisted(() => ({
  calls: [] as {
    protocol: string;
    id: string;
    params: Record<string, unknown>;
    enabled: boolean;
  }[],
  discovery: {} as Record<string, unknown>,
  rendering: {} as Record<string, unknown>,
}));

vi.mock("react-admin", async () => ({
  ...(await vi.importActual<typeof import("react-admin")>("react-admin")),
  useTranslate: () => (key: string) => key,
}));

vi.mock("./LivePreview/usePreview", () => ({
  usePreview: (
    protocol: string,
    id: string,
    params: Record<string, unknown>,
    enabled = true,
  ) => {
    state.calls.push({ protocol, id, params, enabled });
    // the discovery call is the one without the bbox parameter
    return Object.prototype.hasOwnProperty.call(params, "bbox")
      ? { ...state.rendering }
      : { ...state.discovery };
  },
}));

vi.mock("react-leaflet", () => ({
  useMap: () => ({ fitBounds: vi.fn() }),
  ImageOverlay: ({ url }: { url?: string }) => (
    <div data-testid="overlay" data-url={url} />
  ),
}));

vi.mock("../../../MapContainer/GeoJsonMap", () => ({
  default: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="map">{children}</div>
  ),
}));

vi.mock("../../../Input/FeatureGroupEditor", () => ({
  default: ({ geoJson, editable }: { geoJson?: unknown; editable?: boolean }) => (
    <div data-testid="features" data-editable={String(editable)}>
      {String(
        (geoJson as { features?: unknown[] } | undefined)?.features?.length ?? 0,
      )}
    </div>
  ),
}));

const record = {
  id: "layer-1",
  identifier: "wg:topographic",
  service: { id: "service-1" },
};

const successfulDiscovery = (extent: number[] | null) => ({
  supported: true,
  isFetching: false,
  isPending: false,
  error: undefined,
  refetch: vi.fn(),
  data: { configuration: { extent, queryable: false } },
});

const settledRendering = (extra: Record<string, unknown> = {}) => ({
  supported: true,
  isFetching: false,
  isPending: false,
  error: undefined,
  refetch: vi.fn(),
  data: undefined,
  ...extra,
});

beforeEach(() => {
  state.calls.length = 0;
  state.discovery = successfulDiscovery(null);
  state.rendering = settledRendering();
});

describe("ElementPreview", () => {
  it("asks the owning service for the selection and keeps rendering disabled without an extent", () => {
    render(<ElementPreview protocol="WMS" record={record} />);
    expect(state.calls[0]).toEqual({
      protocol: "WMS",
      id: "service-1",
      params: { selection: "wg:topographic" },
      enabled: true,
    });
    expect(state.calls[1].enabled).toBe(false);
    expect(screen.getByText("layerInspection.noPreviewExtent")).toBeInTheDocument();
  });

  it("stays silent without a record which names a selection on a service", () => {
    const { container } = render(<ElementPreview protocol="WMS" record={undefined} />);
    expect(container).toBeEmptyDOMElement();
    expect(state.calls).toHaveLength(2);
    expect(state.calls.every((call) => !call.enabled)).toBe(true);
  });

  it("states an unregistered preview operation without requesting anything", () => {
    state.discovery = { ...state.discovery, supported: false };
    render(<ElementPreview protocol="WFS" record={record} />);
    expect(screen.getByText("livePreview.errors.operation")).toBeInTheDocument();
    expect(state.calls[1].enabled).toBe(false);
  });

  it("renders the advertised image of a layer over the extent", () => {
    state.discovery = successfulDiscovery([-10, 35, 30, 60]);
    state.rendering = settledRendering({ data: { image: "data:image/png;base64,abc" } });
    render(<ElementPreview protocol="WMS" record={record} />);
    expect(state.calls[1].params).toEqual({
      selection: "wg:topographic",
      bbox: "-10,35,30,60",
    });
    expect(screen.getByTestId("map")).toBeInTheDocument();
    expect(screen.getByTestId("overlay")).toHaveAttribute(
      "data-url",
      "data:image/png;base64,abc",
    );
  });

  it("renders the features of a feature type uneditable and states the limit", () => {
    state.discovery = successfulDiscovery([-10, 35, 30, 60]);
    state.rendering = settledRendering({
      data: {
        features: {
          type: "FeatureCollection",
          features: [{ type: "Feature", geometry: null, properties: {} }],
        },
        limit: 500,
        limited: true,
      },
    });
    render(<ElementPreview protocol="WFS" record={record} />);
    expect(screen.getByTestId("features")).toHaveAttribute("data-editable", "false");
    expect(screen.getByTestId("features")).toHaveTextContent("1");
    expect(screen.getByText(/livePreview.limited/)).toBeInTheDocument();
  });

  it("states a feature answer without features instead of an empty map", () => {
    state.discovery = successfulDiscovery([-10, 35, 30, 60]);
    state.rendering = settledRendering({
      data: { features: { type: "FeatureCollection", features: [] } },
    });
    render(<ElementPreview protocol="WFS" record={record} />);
    expect(screen.getByText("livePreview.emptyFeatures")).toBeInTheDocument();
    expect(screen.queryByTestId("map")).not.toBeInTheDocument();
  });

  it("waits for the discovery before it renders", () => {
    state.discovery = { ...state.discovery, isFetching: true };
    render(<ElementPreview protocol="WMS" record={record} />);
    expect(screen.getByLabelText("livePreview.loading")).toBeInTheDocument();
  });

  it("waits for the rendered content once the extent is known", () => {
    state.discovery = successfulDiscovery([-10, 35, 30, 60]);
    state.rendering = settledRendering({ isPending: true, isFetching: true });
    render(<ElementPreview protocol="WMS" record={record} />);
    expect(screen.getByLabelText("livePreview.loading")).toBeInTheDocument();
  });

  it("offers to retry a failed discovery", async () => {
    const refetch = vi.fn();
    state.discovery = {
      supported: true,
      isFetching: false,
      isPending: false,
      error: new Error("gone"),
      refetch,
      data: undefined,
    };
    render(<ElementPreview protocol="WMS" record={record} />);
    expect(screen.getByText("livePreview.errors.discovery")).toBeInTheDocument();
    fireEvent.click(screen.getByText("ra.action.retry"));
    expect(refetch).toHaveBeenCalled();
  });

  it("offers to retry a failed render without loosing the extent", async () => {
    const refetch = vi.fn();
    state.discovery = successfulDiscovery([-10, 35, 30, 60]);
    state.rendering = settledRendering({
      error: new Error("unavailable"),
      refetch,
    });
    render(<ElementPreview protocol="WMS" record={record} />);
    expect(screen.getByText("layerInspection.previewError")).toBeInTheDocument();
    fireEvent.click(screen.getByText("ra.action.retry"));
    expect(refetch).toHaveBeenCalled();
  });
});
