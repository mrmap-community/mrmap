import type { Feature, FeatureCollection } from "geojson";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { latLngBounds } from "leaflet";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  OWSContext,
  OWSResource,
} from "../../ows-lib/OwsContext/core";
import { WFS_OFFERING_CODE } from "../../ows-lib/OwsContext/validation";
import WebFeatureServiceControl from "./GetFeatureControl";

const state = vi.hoisted(() => ({
  context: undefined as unknown as OWSContext,
  reports: [] as [string, string, unknown, number | undefined][],
  removals: [] as string[],
  geoJson: [] as {
    data: FeatureCollection;
    onEachFeature?: (feature: Feature, layer: unknown) => void;
    style?: unknown;
    drawn?: { setStyle: ReturnType<typeof vi.fn> };
  }[],
  opacity: 1,
}));

const map = {
  getBounds: () => latLngBounds([40, -10], [50, 10]),
  getContainer: () => document.body,
  getPane: () => undefined,
  createPane: () => ({ style: {} }),
  on: vi.fn(),
  off: vi.fn(),
};

vi.mock("react-leaflet", () => ({
  useMap: () => map,
  GeoJSON: ({
    data,
    onEachFeature,
    style,
    ref,
  }: {
    data: FeatureCollection;
    onEachFeature?: (feature: Feature, layer: unknown) => void;
    style?: unknown;
    ref?: ((layer: unknown) => void) | { current: unknown } | null;
  }) => {
    // the layer leaflet answers with through the ref, keeping the calls the control makes on it
    const drawn = { setStyle: vi.fn() };
    state.geoJson.push({ data, onEachFeature, style, drawn });
    if (typeof ref === "function") ref(drawn);
    else if (ref !== null && ref !== undefined) ref.current = drawn;
    return <span data-testid="geojson" />;
  },
}));

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
}));

vi.mock("../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  useOwsContextBase: () => ({ owsContext: state.context }),
}));

vi.mock("../MapViewer/MapViewerBase", () => ({
  useMapViewerBase: () => ({
    reportMapLoading: (...args: unknown[]) =>
      state.reports.push(args as [string, string, unknown, number | undefined]),
    removeMapLoading: (id: string) => state.removals.push(id),
    opacityOf: () => state.opacity,
  }),
}));

const collection = (count: number): FeatureCollection => ({
  type: "FeatureCollection",
  features: Array.from({ length: count }, (_, index) => ({
    type: "Feature",
    geometry: { type: "Point", coordinates: [0, index] },
    properties: { name: `feature ${index}` },
  })),
});

const leaf = (
  name: string,
  overrides: Record<string, unknown> = {},
  offering: Record<string, unknown> = {},
  folder = "/0/1",
) =>
  OWSResource.fromPlainObject({
    type: "Feature",
    properties: {
      title: name,
      updated: "2026-01-01T00:00:00Z",
      folder,
      active: true,
      offerings: [
        {
          code: WFS_OFFERING_CODE,
          operations: [
            {
              code: "GetFeature",
              method: "GET",
              href: `https://example.org/wfs?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAME=${name}`,
              type: "application/json",
            },
          ],
          outputFormats: ["application/json"],
          defaultCrs: "EPSG:4326",
          otherCrs: [],
          ...offering,
        },
      ],
      ...overrides,
    },
  });

const context = (features: OWSResource[]) =>
  new OWSContext("urn:uuid:test", features);

const renderControl = () =>
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <WebFeatureServiceControl />
    </QueryClientProvider>,
  );

const successful = (byName: Record<string, FeatureCollection> = {}) => {
  const fetchMock = vi.fn(async (input: string | URL, _options?: RequestInit) => {
    const url = new URL(String(input));
    const name = url.searchParams.get("TYPENAME") ?? "";
    return {
      ok: true,
      status: 200,
      text: async () => JSON.stringify(byName[name] ?? collection(0)),
    };
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
};

beforeEach(() => {
  state.context = context([]);
  state.reports = [];
  state.removals = [];
  state.geoJson = [];
  state.opacity = 1;
});

describe("bounded viewport requests", () => {
  it("requests an active feature type with the negotiated tokens and the view bounded", async () => {
    state.context = context([leaf("a")]);
    const fetchMock = successful();

    renderControl();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const url = new URL(String(fetchMock.mock.calls[0][0]));
    expect(url.searchParams.get("TYPENAME")).toBe("a");
    expect(url.searchParams.get("VERSION")).toBe("2.0.0");
    expect(url.searchParams.get("SRSNAME")).toBe("EPSG:4326");
    expect(url.searchParams.get("BBOX")).toBe("40,-10,50,10,EPSG:4326");
    expect(url.searchParams.get("COUNT")).toBe("500");
    expect(url.searchParams.get("OUTPUTFORMAT")).toBe("application/json");
  });

  it("never requests an inactive type or a type without a GET binding", async () => {
    state.context = context([
      leaf("inactive", { active: false }),
      leaf("post only", {}, {
        operations: [
          {
            code: "GetFeature",
            method: "POST",
            href: "https://example.org/wfs?VERSION=2.0.0&TYPENAME=post%20only",
          },
        ],
      }),
    ]);
    const fetchMock = successful();

    renderControl();

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps every feature type in a request of its own, never batched together", async () => {
    state.context = context([leaf("0", {}, {}, "/0/1"), leaf("1", {}, {}, "/0/2")]);
    const fetchMock = successful();

    renderControl();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const names = fetchMock.mock.calls
      .map(([input]) => new URL(String(input)).searchParams.get("TYPENAME"))
      .sort();
    expect(names).toEqual(["0", "1"]);
  });
});

describe("credentials of the document", () => {
  it("sends an origin matching header assignment with the request", async () => {
    state.context = context([leaf("a")]);
    const operation = state.context.features.find((other) => other.properties.title === "a")!.getWfsOperationByCode("GetFeature")!;
    operation["x-authentication-id"] = "auth-1";
    state.context.authenticationHeaders = [
      {
        id: "auth-1",
        type: "header",
        name: "Authorization",
        value: "Token secret",
        origin: "https://example.org",
      },
    ];
    const fetchMock = successful();

    renderControl();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const options = fetchMock.mock.calls[0][1] as RequestInit;
    expect((options.headers as Headers).get("Authorization")).toBe("Token secret");
    expect(options.credentials).toBe("omit");
  });

  it("refuses to fetch when an assignment names a credential of another origin", async () => {
    state.context = context([leaf("a")]);
    const operation = state.context.features.find((other) => other.properties.title === "a")!.getWfsOperationByCode("GetFeature")!;
    operation["x-authentication-id"] = "missing:auth-1";
    state.context.authenticationHeaders = [
      {
        id: "auth-1",
        type: "header",
        name: "Authorization",
        value: "Token secret",
        origin: "https://other.example",
      },
    ];
    const fetchMock = successful();

    renderControl();

    await waitFor(() =>
      expect(
        state.reports.some(
          ([id, status]) => id.startsWith("feature:") && status === "error",
        ),
      ).toBe(true),
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});



describe("per resource states while the working layers keep rendering", () => {
  it("reports a failing type and renders the working one", async () => {
    state.context = context([leaf("0", {}, {}, "/0/1"), leaf("1", {}, {}, "/0/2")]);
    const fetchMock = vi.fn(async (input: string | URL) => {
      const url = new URL(String(input));
      if (url.searchParams.get("TYPENAME") === "0")
        return { ok: false, status: 500, text: async () => "" };
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify(collection(1)),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    renderControl();

    await waitFor(() =>
      expect(
        state.reports.some(
          ([, status, error]) =>
            status === "error" &&
            (error as { features?: OWSResource[] }).features?.[0]?.properties
              .title === "0",
        ),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(state.geoJson.some((entry) => entry.data.features.length === 1)).toBe(true),
    );
    // the failing type never reaches the map, not even empty
    expect(state.geoJson.every((entry) => entry.data.features.length === 1)).toBe(true);
  });

  it("names a service exception of an HTTP 200 response", async () => {
    state.context = context([leaf("a")]);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        text: async () =>
          '<?xml version="1.0"?><ExceptionReport><Exception code="InvalidParameterValue"><ExceptionText>no such type</ExceptionText></Exception></ExceptionReport>',
      })),
    );

    renderControl();

    await waitFor(() =>
      expect(
        state.reports.some(
          ([, status, error]) =>
            status === "error" &&
            (error as { message?: string }).message?.includes(
              "InvalidParameterValue",
            ),
        ),
      ).toBe(true),
    );
  });

  it("shows a limited result as a bound view instead of a whole store", async () => {
    state.context = context([leaf("a")]);
    successful({ a: collection(500) });

    renderControl();

    await waitFor(() => expect(screen.getByRole("status")).toBeDefined());
  });

  it("drops the loading entry of a layer when it leaves the map", async () => {
    state.context = context([leaf("a")]);
    successful();

    const view = renderControl();
    await waitFor(() => expect(state.geoJson.length).toBe(1));

    act(() => view.unmount());

    expect(state.removals.some((id) => id.startsWith("feature:"))).toBe(true);
  });
});

describe("attributes of a loaded feature", () => {
  it("shows the properties as escaped text, nested values and nulls included", async () => {
    state.context = context([leaf("a")]);
    const dangerous = collection(1);
    dangerous.features[0].properties = {
      marked: "<img src=x onerror=\"alert('xss')\"/>",
      nested: { deep: [1, 2] },
      nothing: null,
    };
    successful({ a: dangerous });

    renderControl();

    await waitFor(() => expect(state.geoJson.length).toBe(1));
    const handlers: Record<string, (event?: unknown) => void> = {};
    state.geoJson[0].onEachFeature?.(dangerous.features[0] as Feature, {
      on: (name: string, handler: (event?: unknown) => void) => {
        handlers[name] = handler;
      },
    });

    act(() => handlers.click?.());

    await waitFor(() =>
      expect(screen.getByText("viewerFeatures.title")).toBeDefined(),
    );
    expect(screen.getByText(/onerror/).textContent).toContain("<img");
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(screen.getByText(/"deep"/).textContent).toContain("1");
    expect(screen.getByText("null")).toBeDefined();
  });
});

describe("the blending of a vector layer", () => {
  it("draws a layer with the style it comes with, at full opacity", async () => {
    state.context = context([leaf("a")]);
    successful({ a: collection(1) });

    renderControl();

    await waitFor(() => expect(state.geoJson.length).toBe(1));
    expect(state.geoJson[0].style).toMatchObject({ opacity: 1, fillOpacity: 0.15 });
  });

  it("dims stroke and fill of a layer to the blending the viewer holds for it", async () => {
    state.opacity = 0.5;
    state.context = context([leaf("a")]);
    successful({ a: collection(1) });

    renderControl();

    await waitFor(() => expect(state.geoJson.length).toBe(1));
    // the ratio of the style is kept: a dimmed layer dims its outline and its fill together
    expect(state.geoJson[0].style).toMatchObject({ opacity: 0.5, fillOpacity: 0.075 });
  });

  it("reaches the already drawn layer when the viewer blends it differently", async () => {
    state.context = context([leaf("a")]);
    successful({ a: collection(1) });
    // one query provider keeps the loaded features while the blending changes
    const provider = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const control = () => (
      <QueryClientProvider client={provider}>
        <WebFeatureServiceControl />
      </QueryClientProvider>
    );
    const { rerender } = render(control());
    await waitFor(() => expect(state.geoJson.length).toBe(1));

    state.opacity = 0.5;
    rerender(control());

    await waitFor(() =>
      expect(state.geoJson.at(-1)?.drawn?.setStyle).toHaveBeenCalledWith(
        expect.objectContaining({ opacity: 0.5, fillOpacity: 0.075 }),
      ),
    );
  });
});

afterEach(() => vi.unstubAllGlobals());