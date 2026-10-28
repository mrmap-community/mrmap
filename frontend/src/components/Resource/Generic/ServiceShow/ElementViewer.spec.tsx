import type { ReactNode } from "react";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ElementViewer from "./ElementViewer";

const state = vi.hoisted(() => ({
  loadingStatus: "idle" as string,
  loadingMessage: undefined as string | undefined,
  errorMessage: undefined as string | undefined,
  unsupported: [] as unknown[],
  addServiceByUrl: vi.fn(),
  resetContext: vi.fn(),
}));

vi.mock("react-admin", async () => ({
  ...(await vi.importActual<typeof import("react-admin")>("react-admin")),
  useTranslate: () => (key: string, options?: Record<string, unknown>) =>
    options?.count !== undefined ? `${key}:${String(options.count)}` : key,
}));

vi.mock("../../../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  OwsContextBase: ({ children }: { children?: ReactNode }) => (
    <div data-testid="provider">{children}</div>
  ),
  useOwsContextBase: () => ({
    addServiceByUrl: state.addServiceByUrl,
    resetContext: state.resetContext,
    loadingStatus: state.loadingStatus,
    loadingMessage: state.loadingMessage,
    errorMessage: state.errorMessage,
  }),
}));

vi.mock("../../../MapViewer/MapViewerBase", () => ({
  MapViewerBase: ({
    children,
    previewExtent,
  }: {
    children?: ReactNode;
    previewExtent?: number[];
  }) => (
    <div data-testid="viewer" data-extent={previewExtent?.join(",")}>
      {children}
    </div>
  ),
  useMapViewerBase: () => ({ unsupportedFeatures: state.unsupported }),
}));

vi.mock("../../../MapContainer/GetMapControl", () => ({
  default: () => <div data-testid="wms-control" />,
}));

vi.mock("../../../MapContainer/GetFeatureControl", () => ({
  default: () => <div data-testid="wfs-control" />,
}));

vi.mock("../../../MapContainer/ResizeAbleMapContainer", () => ({
  default: () => null,
}));

vi.mock("../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "http://localhost:8000/api/",
}));

vi.mock("../../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: "secret" }),
}));

const capabilitiesUrl = "http://localhost:8000/mrmap-proxy/wms/layer/element-1";

const extent = {
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

/** A stored document answering as the single-resource endpoint answers it. */
const documentContext = () => ({
  features: [
    {
      properties: {
        folder: "/1/topographic",
        active: false,
        offerings: [
          {
            operations: [
              {
                code: "GetMap",
                method: "Get",
                href: "http://localhost:8000/mrmap-proxy/wms/1",
                "x-authentication-id": "assigned",
                active: false,
              },
              {
                code: "GetCapabilities",
                method: "Get",
                href: "http://localhost:8000/mrmap-proxy/wms/1",
                "x-authentication-id": "assigned",
                active: false,
              },
            ],
          },
        ],
      },
    },
    {
      properties: {
        folder: "/1/remote",
        active: false,
        offerings: [
          {
            operations: [
              {
                code: "GetMap",
                method: "Get",
                href: "https://remote.example/wms",
                "x-authentication-id": "assigned",
                active: false,
              },
            ],
          },
        ],
      },
    },
  ],
});

beforeEach(() => {
  state.loadingStatus = "idle";
  state.loadingMessage = undefined;
  state.errorMessage = undefined;
  state.unsupported = [];
  state.addServiceByUrl = vi.fn();
  state.resetContext = vi.fn();
});

describe("ElementViewer", () => {
  it("states a missing document without starting a viewer context", () => {
    render(<ElementViewer />);
    expect(screen.getByText("elementViewer.noDocument")).toBeInTheDocument();
    expect(screen.queryByTestId("provider")).not.toBeInTheDocument();
    expect(state.addServiceByUrl).not.toHaveBeenCalled();
  });

  it("reads the document of the element through the registry origin with the token", () => {
    render(<ElementViewer capabilitiesUrl={capabilitiesUrl} extent={extent} />);
    expect(state.resetContext).toHaveBeenCalled();
    const [url, headers, hook] = state.addServiceByUrl.mock.calls[0] as [
      string,
      Headers | undefined,
      unknown,
    ];
    expect(url).toBe(capabilitiesUrl);
    expect(headers?.get("Authorization")).toBe("Token secret");
    expect(typeof hook).toBe("function");
  });

  it("asks a document of another origin without the MrMap token", () => {
    render(
      <ElementViewer capabilitiesUrl="https://remote.example/document.xml" />,
    );
    expect(state.addServiceByUrl.mock.calls[0][1]).toBeUndefined();
  });

  it("lets the advertised resource render and keeps credentials on their origin", () => {
    render(<ElementViewer capabilitiesUrl={capabilitiesUrl} extent={extent} />);
    const hook = state.addServiceByUrl.mock.calls[0][2] as (
      context: unknown,
    ) => unknown;
    const context = documentContext();
    hook(context as never);
    const [proxied, remote] = context.features;
    const operations = (feature: (typeof context.features)[number]) =>
      feature.properties.offerings[0].operations;
    // the rendering operation shows, everything else of the document stays silent
    expect(operations(proxied)[0].active).toBe(true);
    expect(operations(proxied)[1].active).toBe(false);
    expect(proxied.properties.active).toBe(true);
    // an endpoint of this origin keeps the credential it was read with ...
    expect(operations(proxied)[0]["x-authentication-id"]).toBe("assigned");
    // ... while the MrMap token is never handed to a remote origin
    expect(operations(remote)[0]["x-authentication-id"]).toBeUndefined();
    expect(operations(remote)[0].active).toBe(true);
    expect(remote.properties.active).toBe(true);
  });

  it("waits visibly while the document is read", () => {
    state.loadingStatus = "fetching";
    state.loadingMessage = "Downloading capabilities...";
    render(<ElementViewer capabilitiesUrl={capabilitiesUrl} />);
    expect(screen.getByLabelText("elementViewer.loading")).toBeInTheDocument();
    expect(screen.getByText("Downloading capabilities...")).toBeInTheDocument();
    expect(screen.queryByTestId("viewer")).not.toBeInTheDocument();
  });

  it("offers to retry a document which could not be read", () => {
    state.loadingStatus = "error";
    state.errorMessage = "No such layer";
    render(<ElementViewer capabilitiesUrl={capabilitiesUrl} />);
    expect(screen.getByText("No such layer")).toBeInTheDocument();
    fireEvent.click(screen.getByText("ra.action.retry"));
    expect(state.resetContext).toHaveBeenCalledTimes(2);
    expect(state.addServiceByUrl).toHaveBeenCalledTimes(2);
  });

  it("renders the viewer of the single resource once the document is ready", () => {
    state.loadingStatus = "ready";
    render(<ElementViewer capabilitiesUrl={capabilitiesUrl} extent={extent} />);
    const viewer = screen.getByTestId("viewer");
    // the map zooms to the advertised extent of the element
    expect(viewer).toHaveAttribute("data-extent", "8.1,49,8.5,49.4");
    expect(screen.getByTestId("wms-control")).toBeInTheDocument();
    expect(screen.getByTestId("wfs-control")).toBeInTheDocument();
  });

  it("names the resources the viewer cannot render", () => {
    state.loadingStatus = "ready";
    state.unsupported = [{ properties: { folder: "/1/x" } }];
    render(<ElementViewer capabilitiesUrl={capabilitiesUrl} />);
    expect(screen.getByText("viewerUnsupported.summary:1")).toBeInTheDocument();
  });

  it("restarts with another document when the inspected element changes", async () => {
    const { rerender } = render(
      <ElementViewer capabilitiesUrl={capabilitiesUrl} extent={extent} />,
    );
    expect(state.addServiceByUrl).toHaveBeenCalledTimes(1);
    // the key of the call sight remounts the whole viewer by key; rerender the
    // subtree directly to prove the context reloads for another url
    rerender(
      <ElementViewer
        key="next"
        capabilitiesUrl="http://localhost:8000/mrmap-proxy/wms/layer/element-2"
        extent={extent}
      />,
    );
    await waitFor(() =>
      expect(state.addServiceByUrl).toHaveBeenCalledWith(
        "http://localhost:8000/mrmap-proxy/wms/layer/element-2",
        expect.anything(),
        expect.anything(),
      ),
    );
  });
});
