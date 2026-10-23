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
  const { setMap } = useMapViewerBase();
  const { owsContext, updateOwsContext } = useOwsContextBase();
  useEffect(() => {
    setMap(map as unknown as LeafletMap);
  }, [map, setMap]);
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
      <button onClick={() => updateOwsContext(documentWithBbox([10, 20, 30, 40]))}>
        Load document
      </button>
      <button onClick={() => updateOwsContext(documentWithBbox([0, 0, 0, 0]))}>
        Load document without an area
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



