import type { LatLngBounds, Map as LeafletMap } from "leaflet";

import { useEffect } from "react";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { latLng, latLngBounds } from "leaflet";
import { describe, expect, it, vi } from "vitest";

import { OWSResource } from "../../ows-lib/OwsContext/core";
import {
  OwsContextBase,
  useOwsContextBase,
} from "../../react-ows-lib/ContextProvider/OwsContextBase";
import { MapViewerBase, useMapViewerBase } from "./MapViewerBase";
import { boundsToExtent } from "./utils";

/** A document with an area of interest, the way the raw JSON editor hands it over. */
const documentWithBbox = (bbox: number[]) => ({
  type: "FeatureCollection",
  id: "urn:uuid:0f8fad5b-d9cb-469f-a165-70867728950e",
  bbox,
  properties: {
    lang: "en",
    title: "viewer document",
    updated: "2026-10-21T00:00:00Z",
  },
  features: [],
});

/**
 * An activated WMS layer of one endpoint which may advertise scale limits; its GetMap and
 * GetFeatureInfo operations are activated independently, the way the layer tree does.
 */
const layerFeature = (
  name: string,
  folder: string,
  limits: Record<string, number> = {},
) => ({
  type: "Feature",
  id: name,
  properties: {
    title: name,
    updated: "2026-10-21T00:00:00Z",
    folder,
    active: true,
    ...limits,
    offerings: [
      {
        code: "http://www.opengis.net/spec/owc/1.0/req/wms",
        operations: [
          {
            code: "GetMap",
            method: "GET",
            active: true,
            href: `https://example.org/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=${name}`,
          },
          {
            code: "GetFeatureInfo",
            method: "GET",
            active: true,
            href: `https://example.org/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&LAYERS=${name}&QUERY_LAYERS=${name}`,
          },
        ],
      },
    ],
  },
});

const groupFeature = {
  type: "Feature",
  id: "group",
  properties: { title: "group", updated: "2026-10-21T00:00:00Z", folder: "/0" },
};

/** a document with one activated WMS layer */
const documentWithLayer = (limits: Record<string, number> = {}) => ({
  ...documentWithBbox([0, 0, 4, 8]),
  features: [groupFeature, layerFeature("layer", "/0/0", limits)],
});

/**
 * A document with several activated layers of the same endpoint, the way an import hands them over:
 * all of them are renderable and queryable at the very same URL.
 */
const documentWithLayers = (names: string[]) => ({
  ...documentWithBbox([0, 0, 4, 8]),
  features: [
    groupFeature,
    ...names.map((name, index) => layerFeature(name, `/0/${index}`)),
  ],
});

/**
 * The map of the viewer, answering the way leaflet does: a fit chooses a view that is wider than the
 * extent it was asked for, and both a fit and a pan of the user end with a viewport event.
 */
const createMap = (extent = [0, 0, 4, 8]) => {
  const handlers: Record<string, (() => void)[]> = {};
  let view = extent;
  const fire = (event: string) =>
    handlers[event]?.forEach((handler) => handler());
  const map = {
    fitBounds: vi.fn((bounds: LatLngBounds) => {
      view = [
        bounds.getWest() - 1,
        bounds.getSouth() - 1,
        bounds.getEast() + 1,
        bounds.getNorth() + 1,
      ];
      fire("moveend");
      return map;
    }),
    getBounds: () => latLngBounds([view[1], view[0]], [view[3], view[2]]),
    getCenter: () => latLng(30, 0),
    getSize: () => ({ x: 1000, y: 800 }),
    off: (events: string, handler: () => void) => {
      events.split(" ").forEach((event) => {
        handlers[event] = (handlers[event] ?? []).filter(
          (registered) => registered !== handler,
        );
      });
      return map;
    },
    on: (events: string, handler: () => void) => {
      events.split(" ").forEach((event) => {
        handlers[event] = [...(handlers[event] ?? []), handler];
      });
      return map;
    },
    /** pans to the given extent, the way a user does: with a viewport event at the end */
    panTo: (extent: number[]) => {
      view = extent;
      fire("moveend");
      return map;
    },
  };
  return map;
};

const Viewer = ({ map }: { map: ReturnType<typeof createMap> }) => {
  const { setMap, atomicGetMapUrls, atomicGetFeatureInfoUrls } = useMapViewerBase();
  const { owsContext, updateOwsContext } = useOwsContextBase();
  useEffect(() => {
    setMap(map as unknown as LeafletMap);
  }, [map, setMap]);
  const layer = owsContext.features.find(
    (feature) => feature.properties.title === "layer",
  );
  return (
    <>
      <p data-testid="bbox">{owsContext.bbox?.join(",")}</p>
      <p data-testid="document">
        {JSON.stringify({
          id: owsContext.id,
          features: owsContext.features.length,
          title: owsContext.properties.title,
        })}
      </p>
      <p data-testid="getmap">{JSON.stringify(atomicGetMapUrls.map((batch) => batch.features.length))}</p>
      <p data-testid="getfeatureinfo">
        {JSON.stringify(
          atomicGetFeatureInfoUrls.map((query) =>
            query.url.searchParams.get("QUERY_LAYERS"),
          ),
        )}
      </p>
      <p data-testid="mapactivation">
        {String(layer?.getWmsOperationByCode("GetMap")?.active ?? false)}
      </p>
      <button onClick={() => updateOwsContext(documentWithBbox([10, 20, 30, 40]))}>
        Load document
      </button>
      <button onClick={() => updateOwsContext(documentWithBbox([0, 0, 0, 0]))}>
        Load document without an area
      </button>
      <button
        onClick={() =>
          updateOwsContext(documentWithLayer({ maxscaledenominator: 1_000_000 }))
        }
      >
        Load layer with a scale limit
      </button>
      <button onClick={() => updateOwsContext(documentWithLayer())}>
        Load layer without a scale limit
      </button>
      <button onClick={() => updateOwsContext(documentWithLayers(["water", "roads", "labels"]))}>
        Load layers of one service
      </button>
      <button
        onClick={() =>
          updateOwsContext(JSON.parse(JSON.stringify(owsContext)) as never)
        }
      >
        Reload serialized document
      </button>
    </>
  );
};

const renderViewer = (previewExtent?: number[]) => {
  const map = createMap();
  render(
    <OwsContextBase>
      <MapViewerBase previewExtent={previewExtent}>
        <Viewer map={map} />
      </MapViewerBase>
    </OwsContextBase>,
  );
  return map;
};

const areaOfInterest = () => screen.getByTestId("bbox").textContent;
const load = () =>
  fireEvent.click(screen.getByRole("button", { name: "Load document" }));
/** pans the map the way a user would and lets the viewer answer it */
const pan = (map: ReturnType<typeof createMap>, extent: number[]) =>
  act(() => {
    map.panTo(extent);
  });
/** the extent the map was asked to show last */
const lastFit = (map: ReturnType<typeof createMap>) =>
  boundsToExtent((map.fitBounds.mock.calls.at(-1) as [LatLngBounds])[0]);

describe("viewer extent", () => {
  it("shows the area of interest of the document that replaced the state of the viewer", () => {
    const map = renderViewer();
    // a viewer without a document of its own shows the one area of interest it starts with
    expect(lastFit(map)).toEqual([-180, -90, 180, 90]);
    map.fitBounds.mockClear();

    load();

    expect(lastFit(map)).toEqual([10, 20, 30, 40]);
    // the view a fit chose is wider than the area of interest and stays out of the document
    expect(areaOfInterest()).toBe("10,20,30,40");
  });
  it("publishes the viewport of the map into the document when a pan ends", () => {
    const map = renderViewer();
    load();

    pan(map, [1, 2, 3, 4]);

    expect(areaOfInterest()).toBe("1,2,3,4");
    // publishing a viewport is not a new document and leaves the rest of it alone
    expect(screen.getByTestId("document").textContent).toBe(
      JSON.stringify({
        id: "urn:uuid:0f8fad5b-d9cb-469f-a165-70867728950e",
        features: 0,
        title: "viewer document",
      }),
    );
  });
  it("does not fit back the area of interest it published itself", () => {
    const map = renderViewer();
    load();
    const fits = map.fitBounds.mock.calls.length;

    pan(map, [1, 2, 3, 4]);
    pan(map, [5, 6, 7, 8]);

    expect(areaOfInterest()).toBe("5,6,7,8");
    expect(map.fitBounds).toHaveBeenCalledTimes(fits);
  });
  it("shows the same area again after the document was serialized and reloaded", () => {
    const map = renderViewer();
    load();
    pan(map, [1, 2, 3, 4]);
    map.fitBounds.mockClear();

    fireEvent.click(
      screen.getByRole("button", { name: "Reload serialized document" }),
    );

    expect(areaOfInterest()).toBe("1,2,3,4");
    expect(lastFit(map)).toEqual([1, 2, 3, 4]);
  });
  it("applies the extent handed over by the navigation before the one of the document", () => {
    const map = renderViewer([40, 50, 60, 70]);

    expect(lastFit(map)).toEqual([40, 50, 60, 70]);
  });
  it("lets a document show its own area of interest once the user chose a viewport", () => {
    const map = renderViewer([40, 50, 60, 70]);
    load();
    pan(map, [1, 2, 3, 4]);
    map.fitBounds.mockClear();

    load();

    expect(lastFit(map)).toEqual([10, 20, 30, 40]);
  });
  it("keeps the view of a document that carries no usable area of interest", () => {
    const map = renderViewer();
    map.fitBounds.mockClear();

    fireEvent.click(
      screen.getByRole("button", { name: "Load document without an area" }),
    );

    expect(map.fitBounds).not.toHaveBeenCalled();
    expect(areaOfInterest()).toBe("0,0,0,0");
  });
  it("falls back to the document over a broken extent handed over by the navigation", () => {
    const map = renderViewer([Number.NaN, 50, 60, 70]);

    expect(lastFit(map)).toEqual([-180, -90, 180, 90]);
  });
});

/** the mixed document: one resource the viewer renders, two it must name instead of drop */
const mixedFeatures = () => [
  new OWSResource({
    title: "supported",
    updated: "2026-01-01T00:00:00Z",
    folder: "/0",
    offerings: [{
      code: "http://www.opengis.net/spec/owc-geojson/1.0/req/wms",
      operations: [{ code: "GetMap", method: "GET", href: "https://example.org/wms?A", active: true }],
    }],
  }, "supported"),
  new OWSResource({
    title: "post only",
    updated: "2026-01-01T00:00:00Z",
    folder: "/1",
    active: true,
    offerings: [{
      code: "http://www.opengis.net/spec/owc-geojson/1.0/req/wms",
      operations: [{ code: "GetMap", method: "POST", href: "https://example.org/wms?B", active: true }],
    }],
  }, "post only"),
  new OWSResource({
    title: "wmts",
    updated: "2026-01-01T00:00:00Z",
    folder: "/2",
    active: true,
    offerings: [{
      code: "http://www.opengis.net/spec/owc-geojson/1.0/req/wmts",
      operations: [{ code: "GetTile", method: "GET", href: "https://example.org/wmts" }],
    }],
  }, "wmts"),
];

const UnsupportedProbe = () => {
  const { unsupportedFeatures, atomicGetMapUrls } = useMapViewerBase();
  return (
    <p data-testid="unsupported">
      {JSON.stringify({
        unsupported: unsupportedFeatures.map((feature) => feature.id),
        rendered: atomicGetMapUrls.flatMap((request) => request.features.map((feature) => feature.id)),
      })}
    </p>
  );
};

describe("unsupported offerings", () => {
  it("keeps supported resources rendering and names what the viewer cannot render", () => {
    render(
      <OwsContextBase initialFeatures={mixedFeatures()}>
        <MapViewerBase>
          <UnsupportedProbe />
        </MapViewerBase>
      </OwsContextBase>,
    );

    expect(JSON.parse(screen.getByTestId("unsupported").textContent ?? "{}")).toEqual({
      unsupported: ["post only", "wmts"],
      rendered: ["supported"],
    });
  });
});


const loadScaledLayer = () =>
  fireEvent.click(
    screen.getByRole("button", { name: "Load layer with a scale limit" }),
  );
const loadPlainLayer = () =>
  fireEvent.click(
    screen.getByRole("button", { name: "Load layer without a scale limit" }),
  );
const loadLayersOfOneService = () =>
  fireEvent.click(
    screen.getByRole("button", { name: "Load layers of one service" }),
  );
const mapBatches = () => screen.getByTestId("getmap").textContent;
const featureInfoRequests = () =>
  screen.getByTestId("getfeatureinfo").textContent;
const mapActivation = () => screen.getByTestId("mapactivation").textContent;

describe("layer scale limits", () => {
  // the mocked map spans 4 degrees of longitude over 1000 px, i.e. a scale denominator of ~1.59e6;
  // the layer under test is advertised with maxscaledenominator 1e6, so it starts out of scale
  it("does not request a layer which is out of scale at the current view", () => {
    renderViewer();
    loadScaledLayer();

    expect(mapBatches()).toBe("[]");
  });

  it("keeps the activation and the feature info of a layer which is out of scale", () => {
    renderViewer();
    loadScaledLayer();

    // the user activated GetMap and GetFeatureInfo independently; the scale limit only
    // suppresses the rendering and never changes the activation (#606)
    expect(mapActivation()).toBe("true");
    expect(featureInfoRequests()).toBe('["layer"]');
  });

  it("requests the layer once the view is within the advertised limits and again when it leaves them", () => {
    const map = renderViewer();
    loadScaledLayer();

    // panning onto a view spanning 2 degrees answers a scale denominator of ~795000, within the limits
    pan(map, [1, 0, 2, 1]);
    expect(mapBatches()).toBe("[1]");

    // zooming out to a view spanning 8 degrees answers ~3.18e6, out of scale again
    pan(map, [0, 0, 8, 4]);
    expect(mapBatches()).toBe("[]");
  });

  it("renders a layer which advertises no limits at any scale", () => {
    const map = renderViewer();
    loadPlainLayer();

    expect(mapBatches()).toBe("[1]");
    pan(map, [0, 0, 80, 40]);
    expect(mapBatches()).toBe("[1]");
  });
});

describe("feature info queries", () => {
  // the query of a clicked pixel names the layers to look at. WMS counts FEATURE_COUNT per layer,
  // but servers spend it on the whole answer, so a request naming several layers reports the first
  // of them and leaves the rest empty without an error - every layer needs its own request (#700)
  it("asks every layer of one service on its own while the map request batches them", () => {
    renderViewer();
    loadLayersOfOneService();

    // all layers of the endpoint stay rendered with one map request
    expect(mapBatches()).toBe("[3]");
    // and every layer is asked alone, in the order of the document
    expect(featureInfoRequests()).toBe('["water","roads","labels"]');
  });
});



/** reads and changes the blending of every layer of the document */
const OpacityViewer = ({
  map,
  value = 0.5,
}: {
  map: ReturnType<typeof createMap>;
  value?: number;
}) => {
  const { setMap, opacityOf, setLayerOpacity, atomicGetMapUrls } = useMapViewerBase();
  const { owsContext, updateOwsContext } = useOwsContextBase();
  useEffect(() => {
    setMap(map as unknown as LeafletMap);
  }, [map, setMap]);
  const layers = owsContext.features.filter(
    (feature) => feature.getWmsOperationByCode("GetMap") !== undefined,
  );
  return (
    <>
      <p data-testid="opacity">
        {JSON.stringify(
          layers.map((layer) => [layer.properties.title, opacityOf([layer])]),
        )}
      </p>
      <p data-testid="batches">
        {JSON.stringify(
          atomicGetMapUrls.map((batch) =>
            batch.features.map((feature) => feature.properties.title),
          ),
        )}
      </p>
      <button onClick={() => updateOwsContext(documentWithLayers(["first", "second"]))}>
        Load two layers
      </button>
      {layers.map((layer) => (
        <button key={String(layer.id)} onClick={() => setLayerOpacity(layer.properties.folder ?? "", value)}>
          dim {layer.properties.title}
        </button>
      ))}
      {layers.map((layer) => (
        <button key={`${String(layer.id)}-over`} onClick={() => setLayerOpacity(layer.properties.folder ?? "", 1.5)}>
          over {layer.properties.title}
        </button>
      ))}
      {layers.map((layer) => (
        <button key={`${String(layer.id)}-under`} onClick={() => setLayerOpacity(layer.properties.folder ?? "", -1)}>
          under {layer.properties.title}
        </button>
      ))}
    </>
  );
};

const renderOpacityViewer = (value?: number) => {
  const map = createMap();
  render(
    <OwsContextBase>
      <MapViewerBase>
        <OpacityViewer map={map} value={value} />
      </MapViewerBase>
    </OwsContextBase>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Load two layers" }));
  return map;
};
const layerOpacity = () => JSON.parse(screen.getByTestId("opacity").textContent ?? "[]");
const mapRequestsOf = () => JSON.parse(screen.getByTestId("batches").textContent ?? "[]");
const blendLayer = (title: string, action = "dim") =>
  fireEvent.click(screen.getByRole("button", { name: `${action} ${title}` }));

describe("opacity of a layer", () => {
  it("draws every layer at full opacity until the user dims one of them", () => {
    renderOpacityViewer();

    expect(layerOpacity()).toEqual([["first", 1], ["second", 1]]);
    // both layers share one map request, the way the batching always did
    expect(mapRequestsOf()).toEqual([["first", "second"]]);

    blendLayer("first");

    // only the layer the user touched changed, its sibling keeps its full blending
    expect(layerOpacity()).toEqual([["first", 0.5], ["second", 1]]);
  });

  it("asks a map of its own as soon as two layers differ in opacity", () => {
    renderOpacityViewer();
    expect(mapRequestsOf()).toEqual([["first", "second"]]);

    blendLayer("first");
    // one image cannot carry two opacities, so the layer is asked for a map of its own
    expect(mapRequestsOf()).toEqual([["first"], ["second"]]);

    // the very same blending joins them into one request again
    blendLayer("second");
    expect(mapRequestsOf()).toEqual([["first", "second"]]);
  });

  it("keeps the blending of a layer through panning and a reloaded document", () => {
    const map = renderOpacityViewer();
    blendLayer("first");

    pan(map, [1, 2, 3, 4]);
    expect(layerOpacity()).toEqual([["first", 0.5], ["second", 1]]);

    fireEvent.click(screen.getByRole("button", { name: "Load two layers" }));
    expect(layerOpacity()).toEqual([["first", 0.5], ["second", 1]]);
  });

  it("never leaves the span between invisible and fully drawn", () => {
    renderOpacityViewer();

    blendLayer("first", "over");
    expect(layerOpacity()).toEqual([["first", 1], ["second", 1]]);

    blendLayer("second", "under");
    expect(layerOpacity()).toEqual([["first", 1], ["second", 0]]);
  });
});

