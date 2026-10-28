import type { PropsWithChildren } from "react";
import { AdminContext, RecordContextProvider, ResourceContextProvider } from "react-admin";

import { render, screen, waitFor } from "@testing-library/react";
import { latLngBounds } from "leaflet";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OWSResource } from "../../../../ows-lib/OwsContext/core";
import { WMS_OFFERING_CODE } from "../../../../ows-lib/OwsContext/validation";
import wfsMinimal from "../../../../ows-lib/XMLParser/tests/wfs_minimal_2_0_0.xml?raw";
import { OwsContextBase, useOwsContextBase } from "../../../../react-ows-lib/ContextProvider/OwsContextBase";
import ElementLivePreview from "./ElementLivePreview";

/** The capabilities document which advertises one layer, as the proxy of #676 answers it. */
const wmsCapabilities = `<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms"
  xmlns:xlink="http://www.w3.org/1999/xlink">
  <Service><Name>WMS</Name><Title>Rivers</Title></Service>
  <Capability>
    <Request>
      <GetCapabilities><Format>application/vnd.ogc.wms_xml</Format><DCPType><HTTP><Get>
        <OnlineResource xlink:href="https://mrmap.test/mrmap-proxy/wms/layer/6b1"/>
      </Get></HTTP></DCPType></GetCapabilities>
      <GetMap><Format>image/png</Format><DCPType><HTTP><Get>
        <OnlineResource xlink:href="https://mrmap.test/mrmap-proxy/wms/layer/6b1?SERVICE=WMS&amp;REQUEST=GetMap&amp;LAYERS=rivers"/>
      </Get></HTTP></DCPType></GetMap>
    </Request>
    <Layer queryable="1">
      <Name>rivers</Name><Title>Rivers of the region</Title>
      <Abstract>Every river which reaches the sea.</Abstract>
      <EX_GeographicBoundingBox>
        <westBoundLongitude>6.0</westBoundLongitude><eastBoundLongitude>12.0</eastBoundLongitude>
        <southBoundLatitude>49.0</southBoundLatitude><northBoundLatitude>55.0</northBoundLatitude>
      </EX_GeographicBoundingBox>
      <BoundingBox CRS="EPSG:4326" minx="49.0" miny="6.0" maxx="55.0" maxy="12.0"/>
      <Style><Name>default</Name><Title>Default</Title></Style>
    </Layer>
  </Capability>
</WMS_Capabilities>`;

const authState = vi.hoisted(() => ({ token: "s3cret" }));
const asked = vi.hoisted(() => ({
  requests: [] as { url: string; authorization?: string | null }[],
  fitted: [] as number[][],
  answer: (): string => wmsCapabilities,
  status: 200,
  block: undefined as Promise<void> | undefined,
}));

vi.mock("../../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: authState.token }),
}));

const fakeMap = {
  getCenter: () => ({ lat: 51.505, lng: -0.09 }),
  getBounds: () => latLngBounds([49, 6], [55, 12]),
  getSize: () => ({ x: 400, y: 300 }),
  getZoom: () => 6,
  getContainer: () => document.createElement("div"),
  getPane: () => undefined,
  createPane: () => document.createElement("div"),
  invalidateSize: () => undefined,
  on: () => undefined,
  off: () => undefined,
  fitBounds: (bounds: ReturnType<typeof latLngBounds>) => {
    asked.fitted.push([bounds.getSouth(), bounds.getWest(), bounds.getNorth(), bounds.getEast()]);
  },
};

vi.mock("react-leaflet", async () => {
  const { useEffect } = await vi.importActual<typeof import("react")>("react");
  return {
    ScaleControl: () => null,
    useMap: () => fakeMap,
    useMapEvents: () => undefined,
    useMapEvent: () => undefined,
    // the mock hands its map over the way leaflet hands a real one over when it mounts
    MapContainer: ({ children, ref }: PropsWithChildren<{ ref?: (map: unknown) => void }>) => {
      useEffect(() => {
        ref?.(fakeMap);
        return () => ref?.(null);
      }, [ref]);
      return <div data-testid="map">{children}</div>;
    },
  };
});

// the control which asks the document for a map names the resources the document activated
vi.mock("../../../MapContainer/GetMapControl", async () => {
  const provider = await vi.importActual<
    typeof import("../../../../react-ows-lib/ContextProvider/OwsContextBase")
  >("../../../../react-ows-lib/ContextProvider/OwsContextBase");
  return {
    default: () => {
      const { activeFeatures } = provider.useOwsContextBase();
      return (
        <div data-testid="active">
          {activeFeatures.map((feature) => feature.properties.title).join(",")}
        </div>
      );
    },
  };
});
vi.mock("../../../MapContainer/GetFeatureControl", () => ({ default: () => null }));
vi.mock("../../../MapContainer/ResizeAbleMapContainer", () => ({ default: () => null }));

/** The document the map viewer of the same page works on, to keep the two apart. */
const viewerLayer = new OWSResource({
  title: "of the viewer",
  updated: "",
  active: true,
  offerings: [{
    code: WMS_OFFERING_CODE,
    operations: [{ code: "GetMap", method: "GET", href: "https://example.test/wms", active: true }],
  }],
});

const ViewerLayers = () => {
  const { activeFeatures } = useOwsContextBase();
  return <span>{activeFeatures.map((feature) => feature.properties.title).join(",")}</span>;
};

const previewOf = ({
  element,
  resource = "Layer",
}: {
  element?: Record<string, unknown>;
  resource?: "Layer" | "FeatureType";
}) => (
  <AdminContext>
    <ResourceContextProvider value={resource}>
      <RecordContextProvider value={element as never}>
        <ElementLivePreview />
      </RecordContextProvider>
    </ResourceContextProvider>
  </AdminContext>
);

const renderPreview = (
  props: { element?: Record<string, unknown>; resource?: "Layer" | "FeatureType"; withViewerContext?: boolean },
) => {
  const { withViewerContext = false, ...element } = props;
  const preview = previewOf(element);
  return render(
    withViewerContext ? (
      <OwsContextBase initialFeatures={[viewerLayer]}>
        {preview}
        <ViewerLayers />
      </OwsContextBase>
    ) : (
      preview
    ),
  );
};

const layer = {
  id: "6b1",
  name: "rivers",
  capabilitiesUrl: "https://mrmap.test/mrmap-proxy/wms/layer/6b1",
};

beforeEach(() => {
  asked.requests = [];
  asked.fitted = [];
  asked.answer = () => wmsCapabilities;
  asked.status = 200;
  asked.block = undefined;
  authState.token = "s3cret";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: Request | string) => {
      const request = typeof input === "string" ? new Request(input) : input;
      asked.requests.push({
        url: request.url,
        authorization: request.headers.get("authorization"),
      });
      if (asked.block !== undefined) await asked.block;
      return new Response(asked.answer(), {
        status: asked.status,
        headers: { "content-type": "application/xml" },
      });
    }),
  );
});

describe("the live preview of the inspected element", () => {
  it("asks the capabilities document the element names, for the session it is shown in", async () => {
    renderPreview({ element: layer });

    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("Rivers of the region"));

    expect(asked.requests).toHaveLength(1);
    expect(asked.requests[0].url).toBe("https://mrmap.test/mrmap-proxy/wms/layer/6b1");
    expect(asked.requests[0].authorization).toBe("Token s3cret");
  });

  it("shows the map of the viewer for the element, and nothing else of the service", async () => {
    renderPreview({ element: layer });

    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("Rivers of the region"));

    expect(screen.getByTestId("map")).toBeInTheDocument();
    expect(screen.getByTestId("active").textContent).toBe("Rivers of the region");
  });

  it("zooms the map to the extent the document advertises", async () => {
    renderPreview({ element: layer });

    await waitFor(() => expect(asked.fitted).toContainEqual([49, 6, 55, 12]));
  });

  it("names what it is doing while the document is read", async () => {
    let release: () => void = () => undefined;
    asked.block = new Promise<void>((done) => { release = done; });
    renderPreview({ element: layer });

    expect(await screen.findByText("layerInspection.previewLoading")).toBeInTheDocument();

    release();
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("Rivers of the region"));
    expect(screen.queryByText("layerInspection.previewLoading")).toBeNull();
  });

  it("asks nothing and says so when the element names no document", async () => {
    renderPreview({ element: { id: "6b2", name: "lakes" } });

    expect(await screen.findByText("layerInspection.previewNoCapabilities")).toBeInTheDocument();
    expect(asked.requests).toHaveLength(0);
  });

  it("reports a document it could not read and asks it again on request", async () => {
    asked.status = 500;
    renderPreview({ element: layer });

    expect(await screen.findByText(/layerInspection.previewError/)).toBeInTheDocument();

    asked.status = 200;
    const retry = screen.getByRole("button", { name: "ra.action.retry" });
    retry.click();

    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("Rivers of the region"));
    expect(asked.requests).toHaveLength(2);
  });

  it("draws the features of a feature type which has no answer the viewer can draw as not renderable", async () => {
    asked.answer = () => wfsMinimal;
    renderPreview({
      element: { id: "9c2", capabilitiesUrl: "https://mrmap.test/mrmap-proxy/wfs/featuretype/9c2" },
      resource: "FeatureType",
    });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("alert").textContent).toContain("viewerUnsupported.format");
  });

  it("starts from an empty document when another element is inspected", async () => {
    const { rerender } = renderPreview({ element: layer });
    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("Rivers of the region"));

    asked.answer = () => wfsMinimal;
    rerender(
      previewOf({
        element: { id: "9c2", capabilitiesUrl: "https://mrmap.test/mrmap-proxy/wfs/featuretype/9c2" },
        resource: "FeatureType",
      }),
    );

    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("Plain type without optional fields"));
    expect(screen.getByTestId("active").textContent).not.toContain("Rivers");
  });

  it("leaves the document of the map viewer the page shows next to it alone", async () => {
    renderPreview({ element: layer, withViewerContext: true });

    await waitFor(() => expect(screen.getByTestId("active")).toHaveTextContent("Rivers of the region"));

    // the layer the viewer session started with is still the only thing its own document knows
    expect(screen.getByTestId("active").textContent).not.toContain("of the viewer");
    expect(screen.getByText("of the viewer")).toBeInTheDocument();
  });
});
