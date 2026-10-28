import type { ReactNode } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ElementPreview from "./ElementPreview";

vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: ({ operationId }: { operationId: string }) => [{
    props: {
      source: "version",
      choices: operationId === "retrieve_WebMapService"
        ? [{ id: 111, name: "1.1.1" }, { id: 130, name: "1.3.0" }]
        : [{ id: 1, name: "1.0.0" }, { id: 11, name: "1.1.0" }, { id: 200, name: "2.0.0" }],
    },
  }],
}));

const state = vi.hoisted(() => ({
  getOne: {
    data: undefined as Record<string, unknown> | undefined,
    isPending: false,
    isFetching: false,
    error: undefined as Error | undefined,
  },
  getOneParams: undefined as unknown,
}));

vi.mock("react-admin", async () => ({
  ...(await vi.importActual<typeof import("react-admin")>("react-admin")),
  useTranslate: () => (key: string) => key,
  useGetOne: (_resource: string, params: unknown, options?: { enabled?: boolean }) => {
    state.getOneParams = { params, enabled: options?.enabled };
    return {
      data: state.getOne.data,
      isPending: state.getOne.isPending,
      isFetching: state.getOne.isFetching,
      error: state.getOne.error,
      refetch: vi.fn(),
    };
  },
}));

vi.mock("react-leaflet", () => ({
  useMap: () => ({ fitBounds: vi.fn() }),
  ImageOverlay: ({ url }: { url?: string }) => (
    <div data-testid="overlay" data-url={url} />
  ),
}));

vi.mock("../../../MapContainer/GeoJsonMap", () => ({
  default: ({ children }: { children?: ReactNode }) => (
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

vi.mock("../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "http://localhost:8000/api/",
}));

vi.mock("../../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: "secret" }),
}));

const element = {
  id: "element-1",
  identifier: "wg:topographic",
  service: { id: "service-1" },
  bboxLatLon: {
    type: "Polygon",
    coordinates: [
      [
        [8.1, 49.0],
        [8.5, 49.0],
        [8.5, 49.4],
        [8.1, 49.4],
        [8.1, 49.0],
      ],
    ],
  },
};

const unsecuredService = {
  id: "service-1",
  isSecured: false,
  isSpatialSecured: false,
  version: 130,
  operationUrls: [
    { method: 1, operation: 20, url: "https://remote/wms" },
    { method: 1, operation: 30, url: "https://remote/wfs" },
  ],
};

const securedService = {
  ...unsecuredService,
  isSecured: true,
};

const wfsService = { ...securedService, version: 200 };

const featureType = {
  ...element,
  outputFormats: [
    { mimeType: "gml32", stringRepresentation: "GML 3.2" },
    { mimeType: "application/json", stringRepresentation: "JSON" },
  ],
};

const fetchMock = vi.fn();
const createObjectURL = vi.fn(() => "blob:preview");
const revokeObjectURL = vi.fn();

const response = (init: { body?: string; blobType?: string; ok?: boolean; status?: number }) => ({
  ok: init.ok ?? true,
  status: init.status ?? 200,
  blob: async () => new Blob([init.body ?? "img"], { type: init.blobType ?? "image/png" }),
  text: async () => init.body ?? "",
});

const rendered = (ui: ReactNode) =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {ui}
    </QueryClientProvider>,
  );

beforeEach(() => {
  state.getOne.data = undefined;
  state.getOne.isPending = false;
  state.getOne.isFetching = false;
  state.getOne.error = undefined;
  state.getOneParams = undefined;
  fetchMock.mockReset();
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  vi.stubGlobal("fetch", fetchMock);
  Object.assign(URL, { createObjectURL, revokeObjectURL });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ElementPreview", () => {
  it.each([
    [130, "1.3.0", "CRS", "49,8.1,49.4,8.5"],
    [111, "1.1.1", "SRS", "8.1,49,8.5,49.4"],
  ])("resolves WMS version %s from the schema for a remote layer", (version, label, crs, bbox) => {
    rendered(
      <ElementPreview protocol="WMS" element={element} service={{ ...unsecuredService, version }} />,
    );
    const url = new URL(screen.getByTestId("overlay").getAttribute("data-url")!);
    expect(url.searchParams.get("VERSION")).toBe(label);
    expect(url.searchParams.get(String(crs))).toBe("EPSG:4326");
    expect(url.searchParams.get("BBOX")).toBe(bbox);
    expect(url.searchParams.has(crs === "CRS" ? "SRS" : "CRS")).toBe(false);
  });

  it.each([
    [1, "1.0.0", "TYPENAME", "MAXFEATURES", "8.1,49,8.5,49.4"],
    [11, "1.1.0", "TYPENAME", "MAXFEATURES", "49,8.1,49.4,8.5,EPSG:4326"],
    [200, "2.0.0", "TYPENAMES", "COUNT", "49,8.1,49.4,8.5,EPSG:4326"],
  ])("resolves WFS version %s from the schema", async (version, label, typeNames, count, bbox) => {
    fetchMock.mockResolvedValue(response({ body: JSON.stringify({ type: "FeatureCollection", features: [] }) }));
    rendered(
      <ElementPreview protocol="WFS" element={featureType} service={{ ...wfsService, version }} />,
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const url = new URL(String(fetchMock.mock.calls[0][0]));
    expect(url.searchParams.get("VERSION")).toBe(label);
    expect(url.searchParams.get(String(typeNames))).toBe(element.identifier);
    expect(url.searchParams.get(String(count))).toBe("500");
    expect(url.searchParams.get("BBOX")).toBe(bbox);
  });

  it("does not request a version absent from the schema choices", () => {
    rendered(
      <ElementPreview protocol="WMS" element={element} service={{ ...securedService, version: 999 }} />,
    );
    expect(screen.getByText("livePreview.errors.operation")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("asks a secured service through the mrmap proxy with the MrMap token", async () => {
    fetchMock.mockResolvedValue(response({ blobType: "image/png" }));
    rendered(
      <ElementPreview protocol="WMS" element={element} service={securedService} />,
    );
    await waitFor(() => expect(screen.getByTestId("overlay")).toBeInTheDocument());
    const requested = String(fetchMock.mock.calls[0][0]);
    expect(requested).toContain("http://localhost:8000/mrmap-proxy/wms/service-1");
    expect(requested).toContain("LAYERS=wg%3Atopographic");
    expect(requested).toContain("BBOX=49%2C8.1%2C49.4%2C8.5");
    expect(requested).toContain("CRS=EPSG%3A4326");
    expect(new URL(requested).searchParams.get("VERSION")).toBe("1.3.0");
    expect(
      (fetchMock.mock.calls[0][1] as { headers?: Headers }).headers?.get("Authorization"),
    ).toBe("Token secret");
    expect(screen.getByTestId("overlay")).toHaveAttribute("data-url", "blob:preview");
  });

  it("shows a remote unsecured layer straight from its origin without any request of its own", () => {
    rendered(
      <ElementPreview protocol="WMS" element={element} service={unsecuredService} />,
    );
    expect(fetchMock).not.toHaveBeenCalled();
    const overlay = screen.getByTestId("overlay");
    expect(overlay.getAttribute("data-url")).toContain("https://remote/wms");
    expect(overlay.getAttribute("data-url")).toContain("TRANSPARENT=TRUE");
  });

  it("warns when an unsecured service stores no remote url for the operation", () => {
    rendered(
      <ElementPreview
        protocol="WMS"
        element={element}
        service={{ ...unsecuredService, operationUrls: [] }}
      />,
    );
    expect(screen.getByText("livePreview.errors.operation")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("stays silent for an element without identifier or extent", () => {
    const { container } = rendered(
      <ElementPreview
        protocol="WMS"
        element={{ id: "x", service: { id: "service-1" } }}
        service={securedService}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("states an element without an advertised extent without requesting", () => {
    rendered(
      <ElementPreview
        protocol="WMS"
        element={{ ...element, bboxLatLon: undefined, bbox: undefined }}
        service={securedService}
      />,
    );
    expect(screen.getByText("layerInspection.noPreviewExtent")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses a feature type which answers no GeoJSON", () => {
    rendered(
      <ElementPreview
        protocol="WFS"
        element={{ ...featureType, outputFormats: [{ mimeType: "gml32" }] }}
        service={unsecuredService}
      />,
    );
    expect(screen.getByText("livePreview.errors.format")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("renders the features of a feature type uneditable and states the limit", async () => {
    fetchMock.mockResolvedValue(
      response({
        body: JSON.stringify({
          type: "FeatureCollection",
          features: [{ type: "Feature", geometry: null, properties: {} }],
        }),
      }),
    );
    rendered(
      <ElementPreview protocol="WFS" element={featureType} service={wfsService} />,
    );
    await waitFor(() => expect(screen.getByTestId("features")).toBeInTheDocument());
    const requested = String(fetchMock.mock.calls[0][0]);
    expect(requested).toContain("http://localhost:8000/mrmap-proxy/wfs/service-1");
    expect(requested).toContain("TYPENAMES=wg%3Atopographic");
    expect(requested).toContain("OUTPUTFORMAT=application%2Fjson");
    expect(screen.getByTestId("features")).toHaveAttribute("data-editable", "false");
    expect(screen.getByTestId("features")).toHaveTextContent("1");
    expect(screen.getByText(/livePreview.limited/)).toBeInTheDocument();
  });

  it("states an empty feature answer instead of an empty map", async () => {
    fetchMock.mockResolvedValue(
      response({
        body: JSON.stringify({ type: "FeatureCollection", features: [] }),
      }),
    );
    rendered(
      <ElementPreview protocol="WFS" element={featureType} service={wfsService} />,
    );
    await waitFor(() =>
      expect(screen.getByText("livePreview.emptyFeatures")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("map")).not.toBeInTheDocument();
  });

  it("offers to retry a failed request", async () => {
    fetchMock
      .mockResolvedValueOnce(response({ ok: false, status: 502 }))
      .mockResolvedValueOnce(
        response({
          body: JSON.stringify({
            type: "FeatureCollection",
            features: [{ type: "Feature", geometry: null, properties: {} }],
          }),
        }),
      );
    rendered(
      <ElementPreview protocol="WFS" element={featureType} service={wfsService} />,
    );
    await waitFor(() =>
      expect(screen.getByText("layerInspection.previewError")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("ra.action.retry"));
    await waitFor(() => expect(screen.getByTestId("features")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("refuses an xml answer of a feature type as unreadable", async () => {
    fetchMock.mockResolvedValue(response({ body: "<ServiceExceptionReport/>" }));
    rendered(
      <ElementPreview protocol="WFS" element={featureType} service={wfsService} />,
    );
    await waitFor(() =>
      expect(screen.getByText("layerInspection.previewError")).toBeInTheDocument(),
    );
  });

  it("reads the owning service from the element relation away from the service screen", async () => {
    state.getOne.data = securedService;
    fetchMock.mockResolvedValue(response({ blobType: "image/png" }));
    rendered(<ElementPreview protocol="WMS" element={element} />);
    expect(state.getOneParams).toEqual({
      params: {
        id: "service-1",
        meta: { jsonApiParams: { include: "operationUrls" } },
      },
      enabled: true,
    });
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0][0])).toContain("/mrmap-proxy/wms/service-1");
  });

  it("shows an error with retry when the service of the element cannot be read", () => {
    state.getOne.error = new Error("gone");
    rendered(<ElementPreview protocol="WMS" element={element} />);
    expect(screen.getByText("layerInspection.loadError")).toBeInTheDocument();
  });

  it("waits while the service of the element is read", () => {
    state.getOne.isPending = true;
    rendered(<ElementPreview protocol="WMS" element={element} />);
    expect(screen.getByLabelText("livePreview.loading")).toBeInTheDocument();
  });
});
