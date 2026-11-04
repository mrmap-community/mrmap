import type { GeoJsonObject } from "geojson";

import { act, cleanup, render, screen } from "@testing-library/react";
import L from "leaflet";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import FeatureGroupEditor from "./FeatureGroupEditor";

const POLYGON = {
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [0, 1],
      [1, 1],
      [1, 0],
      [0, 0],
    ],
  ],
} as const;

// the maps the editor under test receives through useMap, newest last
const maps = vi.hoisted(() => [] as L.Map[]);

// the drawing events component is a prop sink here: calling its callbacks is
// how a spec says "the user drew something"
type EventsProps = {
  onCreate?: () => void;
  onUpdate?: () => void;
  onRemove?: () => void;
};
const eventsProps = vi.hoisted(() => [] as EventsProps[]);

vi.mock("react-leaflet", () => ({
  useMap: () => maps[maps.length - 1],
}));
vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key.split(".").pop(),
}));
// the drawing controls are their own concern; they would only add leaflet
// plugin side effects to these specs
vi.mock("@geoman-io/leaflet-geoman-free", () => ({}));
vi.mock("../GeomanControl", () => ({ GeomanControl: () => null }));
vi.mock("../GeomanControl/Events", () => ({
  default: (props: EventsProps) => {
    eventsProps.push(props);
    return null;
  },
}));

const createMap = () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const map = L.map(container, { center: [0, 0], zoom: 1 });
  maps.push(map);
  return map;
};

const geoJsonLayers = (map: L.Map) => {
  let count = 0;
  map.eachLayer((layer) => {
    if (layer instanceof L.GeoJSON) count += layer.getLayers().length + 1;
  });
  return count;
};

describe("FeatureGroupEditor", () => {
  let flyToBounds: ReturnType<typeof vi.spyOn>;
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    flyToBounds = vi
      .spyOn(L.Map.prototype, "flyToBounds")
      .mockImplementation(
        (_bounds: L.LatLngBoundsExpression) => maps[maps.length - 1] as L.Map,
      );
    consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    maps.forEach((map) => map.remove());
    maps.length = 0;
    eventsProps.length = 0;
  });

  const renderEditor = (geoJson: GeoJsonObject | string | null | undefined) => {
    const map = createMap();
    render(<FeatureGroupEditor geoJson={geoJson as never} editable={false} />);
    return map;
  };

  it("renders a valid geometry object and fits it into view", () => {
    const polygon = { ...POLYGON } as GeoJsonObject;
    const map = renderEditor(polygon);
    expect(geoJsonLayers(map)).toBe(2); // one group, one drawn polygon
    expect(screen.queryByText("missingCoverage")).not.toBeInTheDocument();
    expect(flyToBounds).toHaveBeenCalledTimes(1);
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("renders a serialized GeoJSON string exactly like the object", () => {
    const serialized = JSON.stringify({
      type: "Feature",
      properties: {},
      geometry: POLYGON,
    });
    const map = renderEditor(serialized);
    expect(geoJsonLayers(map)).toBe(2);
    expect(screen.queryByText("missingCoverage")).not.toBeInTheDocument();
    expect(flyToBounds).toHaveBeenCalledTimes(1);
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("renders a collection whose member geometries are serialized", () => {
    // the shape AccessRulesSummary builds from the API's serialized `allowedArea`
    const collection = {
      type: "FeatureCollection",
      features: [
        { type: "Feature", properties: {}, geometry: JSON.stringify(POLYGON) },
      ],
    };
    const map = renderEditor(collection as never);
    expect(geoJsonLayers(map)).toBe(2);
    expect(screen.queryByText("missingCoverage")).not.toBeInTheDocument();
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("shows the hint for an object without a GeoJSON type instead of throwing", () => {
    const map = renderEditor({} as never);
    expect(geoJsonLayers(map)).toBe(0);
    expect(screen.getByText("missingCoverage")).toBeInTheDocument();
    expect(flyToBounds).not.toHaveBeenCalled();
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError.mock.calls[0][1]).toEqual({ typeof: "object", type: null });
  });

  it("shows the hint for a LatLngBounds-shaped object instead of throwing", () => {
    const boundsShape = {
      _southEast: { lat: 1, lng: 1 },
      _northWest: { lat: 0, lng: 0 },
    } as never;
    const map = renderEditor(boundsShape);
    expect(geoJsonLayers(map)).toBe(0);
    expect(screen.getByText("missingCoverage")).toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError.mock.calls[0][1]).toEqual({ typeof: "object", type: null });
  });

  it("shows the hint for an unparsable string and says what arrived", () => {
    const map = renderEditor("not json");
    expect(geoJsonLayers(map)).toBe(0);
    expect(screen.getByText("missingCoverage")).toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(consoleError.mock.calls[0][1]).toEqual({ typeof: "string", type: null });
  });

  it("shows the hint quietly for absent values", () => {
    for (const absent of [null, undefined, ""]) {
      const map = renderEditor(absent);
      expect(geoJsonLayers(map)).toBe(0);
      expect(screen.getByText("missingCoverage")).toBeInTheDocument();
      expect(consoleError).not.toHaveBeenCalled();
      cleanup();
      map.remove();
      maps.pop();
    }
  });

  it("shows the hint for valid GeoJSON without any position", () => {
    const empty = { type: "Feature", properties: {}, geometry: null } as never;
    const map = renderEditor(empty);
    expect(geoJsonLayers(map)).toBe(1); // the tolerated empty feature group
    expect(screen.getByText("missingCoverage")).toBeInTheDocument();
    expect(flyToBounds).not.toHaveBeenCalled();
    expect(consoleError).not.toHaveBeenCalled();
  });

  it("replaces the drawn layer and the hint when the value changes", () => {
    const map = createMap();
    const { rerender } = render(
      <FeatureGroupEditor geoJson={POLYGON as never} editable={false} />,
    );
    expect(geoJsonLayers(map)).toBe(2);
    rerender(<FeatureGroupEditor geoJson={"{}" as never} editable={false} />);
    expect(geoJsonLayers(map)).toBe(0);
    expect(screen.getByText("missingCoverage")).toBeInTheDocument();
    rerender(
      <FeatureGroupEditor
        geoJson={JSON.stringify(POLYGON)}
        editable={false}
      />,
    );
    expect(geoJsonLayers(map)).toBe(2);
    expect(screen.queryByText("missingCoverage")).not.toBeInTheDocument();
  });

  it("keeps the map controls clickable under the hint", () => {
    renderEditor({} as never);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveStyle({ "pointer-events": "none" });
    // leaflet's zoom control occupies the top left of these cards, so the
    // hint starts below that band instead of covering it
    expect(alert).toHaveStyle({ top: "76px" });
  });

  it("drops the hint as soon as the drawing has content", () => {
    const map = createMap();
    render(
      <FeatureGroupEditor
        geoJson={{} as never}
        geoJsonCallback={() => undefined}
        editable
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    L.polygon([
      [0, 0],
      [0, 1],
      [1, 1],
    ]).addTo(map);
    const drawn = eventsProps[eventsProps.length - 1];
    act(() => drawn.onUpdate?.());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    // removing the drawing again leaves nothing to show, so the hint is back
    map.eachLayer((layer) => {
      if (layer instanceof L.Polygon) layer.remove();
    });
    act(() => drawn.onRemove?.());
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
