import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LivePreview from "./LivePreview";

const state = vi.hoisted(() => ({
  record: { id: "service-1" } as Record<string, unknown>,
  choices: {
    data: undefined as Record<string, unknown>[] | undefined,
    total: 0,
    error: undefined as Error | undefined,
    isPending: false,
  },
  preview: {
    data: undefined as Record<string, unknown> | undefined,
    isFetching: false,
    error: undefined as { code: string } | undefined,
    supported: true,
    refetch: vi.fn(),
  },
  addServiceByUrl: vi.fn(async () => undefined),
  navigate: vi.fn(),
}));

vi.mock("react-admin", async () => ({
  ...(await vi.importActual<typeof import("react-admin")>("react-admin")),
  useTranslate: () => (key: string, options?: Record<string, unknown>) =>
    options?.count !== undefined ? `${key}:${String(options.count)}` : key,
  useRecordContext: () => state.record,
  useGetList: () => ({
    data: state.choices.data,
    total: state.choices.total,
    error: state.choices.error,
    isPending: state.choices.isPending,
    isFetching: false,
    refetch: vi.fn(),
  }),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => state.navigate,
}));

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="map">{children}</div>
  ),
  Rectangle: ({
    eventHandlers,
    bounds,
  }: {
    eventHandlers?: { click?: () => void };
    bounds: { toString: () => string };
  }) => (
    <div
      data-testid="rectangle"
      data-bounds={bounds.toString()}
      onClick={() => eventHandlers?.click?.()}
    />
  ),
  useMap: () => ({ fitBounds: vi.fn() }),
}));

vi.mock("../../../../MapContainer/ResizeAbleMapContainer", () => ({
  default: () => null,
}));

vi.mock("../ElementViewer", async () => ({
  // the panel is not rendered here, but the helpers which hand an element to a
  // viewer are the real ones, so what the preview asks with is what it asks
  ...(await vi.importActual<typeof import("../ElementViewer")>(
    "../ElementViewer",
  )),
  default: ({
    capabilitiesUrl,
    extent,
  }: {
    capabilitiesUrl?: unknown;
    extent?: unknown;
  }) => (
    <div
      data-testid="element-viewer"
      data-url={String(capabilitiesUrl ?? "")}
      data-extent={JSON.stringify(extent)}
    />
  ),
}));

vi.mock("./usePreview", async () => {
  const { PreviewFailure } = await vi.importActual<typeof import("./usePreview")>(
    "./usePreview",
  );
  return {
    PreviewFailure,
    serviceResource: {
      WMS: "WebMapService",
      WFS: "WebFeatureService",
      CSW: "CatalogueService",
    },
    usePreview: () => ({ ...state.preview, supported: state.preview.supported }),
  };
});

vi.mock("../../../../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  OwsContextBase: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  useOwsContextBase: () => ({ addServiceByUrl: state.addServiceByUrl }),
}));

vi.mock("../../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "http://localhost:8000/api/",
}));

vi.mock("../../../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: "secret" }),
}));

const polygon = {
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
};

const layers = [
  {
    id: "layer-1",
    identifier: "roads",
    title: "Roads",
    capabilitiesUrl: "http://localhost:8000/mrmap-proxy/wms/layer/layer-1",
    bboxLatLon: polygon,
  },
  {
    id: "layer-2",
    identifier: "rivers",
    title: "Rivers",
    capabilitiesUrl: "http://localhost:8000/mrmap-proxy/wms/layer/layer-2",
    bboxLatLon: polygon,
  },
  {
    id: "layer-3",
    identifier: "linked",
    title: "Linked",
    capabilitiesUrl: "http://localhost:8000/mrmap-proxy/wms/layer/layer-3",
    bboxLatLon: polygon,
  },
];

const open = () => {
  fireEvent.click(screen.getByText("livePreview.title"));
};

const rendered = (protocol: "WMS" | "WFS" | "CSW") =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <LivePreview protocol={protocol} />
    </QueryClientProvider>,
  );

beforeEach(() => {
  state.record = { id: "service-1" };
  state.choices.data = undefined;
  state.choices.total = 0;
  state.choices.error = undefined;
  state.choices.isPending = false;
  state.preview.data = undefined;
  state.preview.isFetching = false;
  state.preview.error = undefined;
  state.preview.supported = true;
  state.addServiceByUrl = vi.fn(async () => undefined);
  state.navigate = vi.fn();
});

describe("LivePreview", () => {
  it("renders the chosen element with the viewer of its single document", async () => {
    state.choices.data = layers;
    state.choices.total = 2;
    rendered("WMS");
    open();
    // the first named element is chosen by default and rendered by its own document
    await waitFor(() =>
      expect(screen.getByTestId("element-viewer")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("element-viewer")).toHaveAttribute(
      "data-url",
      "http://localhost:8000/mrmap-proxy/wms/layer/layer-1",
    );
    // another choice renders another element
    fireEvent.mouseDown(screen.getByLabelText("livePreview.layer"));
    fireEvent.click(await screen.findByText("Rivers"));
    await waitFor(() =>
      expect(screen.getByTestId("element-viewer")).toHaveAttribute(
        "data-url",
        "http://localhost:8000/mrmap-proxy/wms/layer/layer-2",
      ),
    );
  });

  it("hands the chosen element to the full viewer through its own document", async () => {
    state.choices.data = layers;
    state.choices.total = 2;
    rendered("WMS");
    open();
    fireEvent.click(await screen.findByText("ra.action.mapviewer"));
    await waitFor(() => expect(state.addServiceByUrl).toHaveBeenCalled());
    const [url, headers, hook] = state.addServiceByUrl.mock
      .calls[0] as unknown as [string, Headers, unknown];
    expect(url).toBe("http://localhost:8000/mrmap-proxy/wms/layer/layer-1");
    expect(headers.get("Authorization")).toBe("Token secret");
    expect(typeof hook).toBe("function");
    expect(state.navigate).toHaveBeenCalledWith(
      "/viewer",
      expect.objectContaining({
        state: { previewExtent: [8.1, 49, 8.5, 49.4] },
      }),
    );
  });

  it("states a linked selection outside the loaded page without rendering it", async () => {
    state.choices.data = [layers[0]];
    state.choices.total = 1;
    state.preview.data = {
      source: "https://csw.test/record",
      fetchedAt: new Date(0).toISOString(),
      records: [
        {
          identifier: "record-1",
          title: "First",
          extent: [8, 49, 9, 50],
          previews: [
            {
              protocol: "WMS",
              serviceId: "service-2",
              selection: "hidden",
              title: "Linked service",
            },
          ],
        },
      ],
      matched: 1,
      start: 1,
    };
    rendered("CSW");
    open();
    fireEvent.click(await screen.findByText("livePreview.previewLinked"));
    expect(
      await screen.findByText("livePreview.selectOutsidePage"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("element-viewer")).not.toBeInTheDocument();
  });

  it("states an empty selection list and a failed one with retry", async () => {
    state.choices.data = [];
    state.choices.total = 0;
    const { unmount } = rendered("WMS");
    open();
    expect(
      await screen.findByText("livePreview.emptySelections"),
    ).toBeInTheDocument();
    unmount();
    state.choices.error = new Error("gone");
    render(
      <QueryClientProvider client={new QueryClient()}>
        <LivePreview protocol="WMS" />
      </QueryClientProvider>,
    );
    open();
    expect(
      await screen.findByText("livePreview.errors.discovery"),
    ).toBeInTheDocument();
  });

  it("pages through catalogue records and maps their coverages", async () => {
    state.preview.data = {
      source: "https://csw.test/record",
      fetchedAt: new Date(0).toISOString(),
      records: [
        {
          identifier: "record-1",
          title: "First",
          extent: [8, 49, 9, 50],
          previews: [
            {
              protocol: "WMS",
              serviceId: "service-2",
              selection: "linked",
              title: "Linked service",
            },
          ],
        },
      ],
      matched: 40,
      start: 1,
      next: 21,
    };
    rendered("CSW");
    open();
    expect(await screen.findByTestId("map")).toBeInTheDocument();
    expect(screen.getByTestId("rectangle")).toBeInTheDocument();
    expect(screen.getByText("First")).toBeInTheDocument();
    // the registered resource of a record opens its own live preview
    state.choices.data = layers;
    state.choices.total = 2;
    fireEvent.click(
      screen.getByText("livePreview.previewLinked"),
    );
    await waitFor(() =>
      expect(screen.getByTestId("element-viewer")).toBeInTheDocument(),
    );
  });

  it("warns when the catalogue preview operation is unsupported", async () => {
    state.preview.supported = false;
    rendered("CSW");
    open();
    expect(
      await screen.findByText("livePreview.errors.operation"),
    ).toBeInTheDocument();
  });

  it("reports a failed catalogue request with retry", async () => {
    state.preview.error = { code: "denied" };
    rendered("CSW");
    open();
    expect(
      await screen.findByText("livePreview.errors.denied"),
    ).toBeInTheDocument();
  });
});
