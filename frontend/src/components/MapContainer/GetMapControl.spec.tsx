import type { PropsWithChildren } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render as testingRender,
  screen,
  waitFor,
} from "@testing-library/react";
import { latLng, latLngBounds, point } from "leaflet";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { OptimizedUrlsMap } from "../../ows-lib/OwsContext/core";
import WebMapServiceControl from "./GetMapControl";

const state = vi.hoisted(() => ({
  context: {} as import("../../ows-lib/OwsContext/types").OWSContext,
  maps: [] as OptimizedUrlsMap[],
  info: [] as OptimizedUrlsMap[],
  opacity: 1,
  onContextMenu: undefined as undefined | ((event: unknown) => void),
  bounds: undefined as undefined | import("leaflet").LatLngBounds,
  displayedTimes: {} as Record<string, string>,
  viewportHandlers: [] as (() => void)[],
}));
const map = {
  getContainer: () => document.body,
  getBounds: () => state.bounds ?? latLngBounds([0, 0], [10, 10]),
  getSize: () => point(256, 256),
  on: vi.fn((_events: string, handler: () => void) => {
    state.viewportHandlers.push(handler);
  }),
  off: vi.fn(),
};
vi.mock("react-leaflet", () => ({
  useMap: () => map,
  useMapEvent: (_name: string, handler: typeof state.onContextMenu) => {
    if (_name === "contextmenu") state.onContextMenu = handler;
  },
  Marker: ({ children }: PropsWithChildren) => <>{children}</>,
  Popup: ({ children }: PropsWithChildren) => <>{children}</>,
  Tooltip: () => null,
}));
vi.mock("../Resource/Generic/ServiceShow/LivePreview/LivePreview", () => ({
  FeatureInfoResult: ({ text }: { text: string }) => <pre>{text}</pre>,
}));
vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
  Link: ({ to, children }: PropsWithChildren<{ to: string }>) => (
    <a href={to}>{children}</a>
  ),
}));
vi.mock("../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  useOwsContextBase: () => ({ owsContext: state.context }),
}));
vi.mock("../MapViewer/MapViewerBase", () => ({
  useMapViewerBase: () => ({
    selectedCrs: { stringRepresentation: "EPSG:4326", isXyOrder: true },
    atomicGetMapUrls: state.maps,
    atomicGetFeatureInfoUrls: state.info,
    opacityOf: () => state.opacity,
    displayedTimes: state.displayedTimes,
  }),
}));
vi.mock("./AuthImageOverlay", () => ({
  AuthImageOverlay: ({
    optimiuedUrl,
    opacity,
  }: {
    optimiuedUrl: OptimizedUrlsMap;
    opacity?: number;
  }) => (
    <span data-testid="image-url" data-opacity={opacity}>
      {optimiuedUrl.url.href}
    </span>
  ),
}));
const render = (ui: import("react").ReactNode) =>
  testingRender(
    <QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>,
  );
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
const batch = (params: string): OptimizedUrlsMap => ({
  url: new URL(`https://example.org/wms?VERSION=1.3.0&${params}`),
  features: [],
  operations: [
    { code: "GetMap", method: "GET", href: "https://example.org/wms" },
  ],
});
beforeEach(() => {
  state.context = {} as typeof state.context;
  state.maps = [];
  state.info = [];
  state.opacity = 1;
  state.bounds = undefined;
  state.displayedTimes = {};
  state.viewportHandlers.length = 0;
});

test("draws a map request at full blending until the viewer holds another for it", () => {
  state.maps = [batch("LAYERS=a")];
  const { rerender } = render(<WebMapServiceControl />);
  expect(screen.getByTestId("image-url")).toHaveAttribute("data-opacity", "1");

  // the blending changes while the map request stays the very same one
  state.opacity = 0.25;
  rerender(<WebMapServiceControl />);
  expect(screen.getByTestId("image-url")).toHaveAttribute("data-opacity", "0.25");
});

test("the final map URL preserves configured positional styles and vendor parameters", () => {
  state.maps = [batch("LAYERS=a,b&STYLES=outline,fill&token=map")];
  render(<WebMapServiceControl />);
  const url = new URL(screen.getByTestId("image-url").textContent!);
  expect(url.searchParams.get("LAYERS")).toBe("a,b");
  expect(url.searchParams.get("STYLES")).toBe("outline,fill");
  expect(url.searchParams.get("token")).toBe("map");
  expect(url.searchParams.get("WIDTH")).toBe("256");
});

test("the final feature info URL preserves map layers, query subset and styles", async () => {
  state.info = [
    batch(
      "LAYERS=backdrop,a,b&QUERY_LAYERS=a,b&STYLES=,outline,fill&token=info",
    ),
  ];
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    text: async () => '{"features":[]}',
    headers: new Headers({ "content-type": "application/json" }),
  });
  vi.stubGlobal("fetch", fetch);
  render(<WebMapServiceControl />);
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  const url = new URL(fetch.mock.calls[0][0]);
  expect(url.searchParams.get("LAYERS")).toBe("backdrop,a,b");
  expect(url.searchParams.get("QUERY_LAYERS")).toBe("a,b");
  expect(url.searchParams.get("STYLES")).toBe(",outline,fill");
  expect(url.searchParams.get("token")).toBe("info");
  expect(url.searchParams.get("I")).toBe("20");
  expect(url.searchParams.get("J")).toBe("30");
  expect(url.searchParams.get("X")).toBeNull();
  expect(url.searchParams.get("Y")).toBeNull();
  expect(url.searchParams.get("INFO_FORMAT")).toBe("application/json");
  expect(url.searchParams.get("FEATURE_COUNT")).toBe("10");
});

test("a 1.1.1 query answers through X/Y pixels and drops the 1.3.0 pair", async () => {
  state.info = [
    {
      url: new URL(
        "https://example.org/wms?VERSION=1.1.1&SRS=EPSG:4326&QUERY_LAYERS=a&I=99&J=98",
      ),
      features: [],
      operations: [
        {
          code: "GetFeatureInfo",
          method: "GET",
          href: "https://example.org/wms",
        },
      ],
    },
  ];
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    text: async () => '{"features":[]}',
    headers: new Headers({ "content-type": "application/json" }),
  });
  vi.stubGlobal("fetch", fetch);
  render(<WebMapServiceControl />);
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  const params = new URL(fetch.mock.calls[0][0]).searchParams;
  expect(params.get("X")).toBe("20");
  expect(params.get("Y")).toBe("30");
  expect(params.get("I")).toBeNull();
  expect(params.get("J")).toBeNull();
});

test("keeps the defaults for requests without styles or feature info map layers", async () => {
  state.maps = [batch("LAYERS=a")];
  state.info = [batch("QUERY_LAYERS=a")];
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    text: async () => "plain",
    headers: new Headers({ "content-type": "text/plain" }),
  });
  vi.stubGlobal("fetch", fetch);
  render(<WebMapServiceControl />);
  expect(
    new URL(screen.getByTestId("image-url").textContent!).searchParams.get(
      "STYLES",
    ),
  ).toBe("");
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  const params = new URL(fetch.mock.calls[0][0]).searchParams;
  expect(params.get("LAYERS")).toBe("a");
  expect(params.get("STYLES")).toBe("");
});

test("fetches unprotected queries inline and offers the raw response on failure", async () => {
  state.info = [batch("QUERY_LAYERS=a,b")];
  const fetch = vi.fn().mockRejectedValue(new Error("network down"));
  vi.stubGlobal("fetch", fetch);
  render(<WebMapServiceControl />);
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );
  expect(screen.getByText("viewerFeatureInfo.loading")).toBeInTheDocument();
  expect(screen.getByText("a,b")).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "viewerFeatureInfo.error",
  );
  const link = screen.getByRole("link");
  expect(link).toHaveTextContent("viewerFeatureInfo.raw");
  expect(
    new URL(link.getAttribute("href")!).searchParams.get("QUERY_LAYERS"),
  ).toBe("a,b");
});

test("fetches protected identify results with the assigned headers and blocks missing credentials", async () => {
  state.context.authenticationHeaders = [
    {
      id: "info",
      type: "header",
      origin: "https://example.org",
      name: "Authorization",
      value: "Basic secret",
    },
  ];
  state.info = [batch("QUERY_LAYERS=a")];
  state.info[0].operations[0]["x-authentication-id"] = "info";
  const fetch = vi.fn().mockResolvedValue({
    ok: true,
    text: async () => "<script>unsafe</script>",
    headers: new Headers({ "content-type": "text/html" }),
  });
  vi.stubGlobal("fetch", fetch);
  const { rerender } = render(<WebMapServiceControl />);
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  const options = fetch.mock.calls[0][1];
  expect(options.headers.get("Authorization")).toBe("Basic secret");
  expect(options).toMatchObject({
    redirect: "error",
    credentials: "omit",
    signal: expect.any(AbortSignal),
  });
  expect(
    await screen.findByText("<script>unsafe</script>"),
  ).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  state.context = { ...state.context, authenticationHeaders: [] };
  rerender(
    <QueryClientProvider client={new QueryClient()}>
      <WebMapServiceControl />
    </QueryClientProvider>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("viewerAuth.missing");
  expect(fetch).toHaveBeenCalledTimes(1);
});

test("collapsing and reopening keeps results and map requests unchanged; clear aborts pending queries", async () => {
  state.maps = [batch("LAYERS=background")];
  state.info = [batch("QUERY_LAYERS=places")];
  let signal: AbortSignal | undefined;
  const fetched = vi.fn((_url: string, options: RequestInit) => {
    signal = options.signal as AbortSignal;
    return new Promise<Response>(() => {});
  });
  vi.stubGlobal("fetch", fetched);
  render(<WebMapServiceControl />);
  const mapUrl = screen.getByTestId("image-url").textContent;
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );
  await waitFor(() => expect(fetched).toHaveBeenCalledTimes(1));
  fireEvent.click(
    screen.getByRole("button", { name: "viewerFeatureInfo.collapse" }),
  );
  expect(
    screen.queryByRole("region", { name: "viewerFeatureInfo.title" }),
  ).not.toBeInTheDocument();
  expect(signal?.aborted).toBe(false);
  fireEvent.click(
    screen.getByRole("button", { name: "viewerFeatureInfo.reopen" }),
  );
  expect(
    screen.getByRole("region", { name: "viewerFeatureInfo.title" }),
  ).toBeVisible();
  expect(fetched).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId("image-url").textContent).toBe(mapUrl);
  fireEvent.click(
    screen.getByRole("button", { name: "viewerFeatureInfo.clear" }),
  );
  expect(signal?.aborted).toBe(true);
});

// A WMS server may spend the FEATURE_COUNT of a request on the queried layers in the order of the
// request instead of counting it per layer: a query naming several layers then answers the first of
// them and leaves the others empty without an error. The viewer asks one layer per request, so every
// layer of the map gets its own features (#700).
/** the answer of an upstream service which counts features over the whole query */
const countsFeaturesOverTheQuery = (url: string) => {
  const params = new URL(url).searchParams;
  const [firstLayer] = (params.get("QUERY_LAYERS") ?? "").split(",");
  const count = Number(params.get("FEATURE_COUNT"));
  return Promise.resolve({
    ok: true,
    text: async () =>
      Array.from({ length: count }, () => `${firstLayer} feature`).join("\n"),
    headers: new Headers({ "content-type": "text/plain" }),
  });
};

test("answers every layer although the server spends the feature count over the query", async () => {
  state.info = [
    batch("QUERY_LAYERS=water&FEATURE_COUNT=1"),
    batch("QUERY_LAYERS=roads&FEATURE_COUNT=1"),
  ];
  const fetched = vi.fn(countsFeaturesOverTheQuery);
  vi.stubGlobal("fetch", fetched);
  render(<WebMapServiceControl />);
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );

  expect(await screen.findByText("water feature")).toBeInTheDocument();
  expect(screen.getByText("roads feature")).toBeInTheDocument();
  // one request per layer, each naming only the layer it asks for
  expect(fetched).toHaveBeenCalledTimes(2);
  expect(
    fetched.mock.calls
      .map(([url]) => new URL(url).searchParams.get("QUERY_LAYERS"))
      .sort(),
  ).toEqual(["roads", "water"]);
});

test("keeps the answer of one layer apart from the failure and retry of another", async () => {
  state.info = [batch("QUERY_LAYERS=water"), batch("QUERY_LAYERS=roads")];
  const fetched = vi.fn((url: string) =>
    new URL(url).searchParams.get("QUERY_LAYERS") === "roads"
      ? Promise.reject(new Error("network down"))
      : Promise.resolve({
          ok: true,
          text: async () => "water feature",
          headers: new Headers({ "content-type": "text/plain" }),
        }),
  );
  vi.stubGlobal("fetch", fetched);
  render(<WebMapServiceControl />);
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );

  expect(await screen.findByText("water feature")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "viewerFeatureInfo.error",
  );
  // the failing layer offers its own retry and the answered layer keeps its result
  expect(
    screen.getByRole("button", { name: "ra.action.retry" }),
  ).toBeInTheDocument();
  expect(screen.getByText("water feature")).toBeInTheDocument();
});

test("aborts the query of the identify selection that a newer one replaces", async () => {
  state.info = [batch("QUERY_LAYERS=water")];
  const signals: AbortSignal[] = [];
  const fetched = vi.fn((_url: string, options: RequestInit) => {
    signals.push(options.signal as AbortSignal);
    return new Promise<Response>(() => {});
  });
  vi.stubGlobal("fetch", fetched);
  render(<WebMapServiceControl />);
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );
  await waitFor(() => expect(fetched).toHaveBeenCalledTimes(1));

  act(() =>
    state.onContextMenu?.({
      latlng: latLng(6, 6),
      containerPoint: point(40, 50),
    }),
  );
  await waitFor(() => expect(fetched).toHaveBeenCalledTimes(2));
  // the obsolete query is cancelled, so its late answer cannot replace the new selection
  await waitFor(() => expect(signals[0]?.aborted).toBe(true));
  expect(new URL(fetched.mock.calls[1][0]).searchParams.get("I")).toBe("40");
});

// A new time on the same layer must not blank the map: the overlay stays mounted so it can keep
// the frame it draws until the new time has an answer; everything else which changes the request
// answers with a fresh overlay whose image the map cannot show (#705).
test("a new selected time keeps the very same image overlay", () => {
  state.maps = [batch("LAYERS=a&TIME=2026-01-01T00%3A00%3A00Z")];
  const { rerender } = render(<WebMapServiceControl />);
  const before = screen.getByTestId("image-url");

  state.maps = [batch("LAYERS=a&TIME=2026-01-01T00%3A05%3A00Z")];
  rerender(
    <QueryClientProvider client={new QueryClient()}>
      <WebMapServiceControl />
    </QueryClientProvider>,
  );

  // react updated the element in place, so its overlay can keep drawing the arrived frame,
  // while the request itself goes out with the newly selected time
  expect(screen.getByTestId("image-url")).toBe(before);
  expect(before.textContent).toContain("TIME=2026-01-01T00%3A05%3A00Z");
});

test("a new selection through a DIM_<name> time dimension keeps the very same image overlay", () => {
  const withDate = (time: string): OptimizedUrlsMap => ({
    url: new URL(
      `https://example.org/wms?VERSION=1.3.0&LAYERS=a&TRANSPARENT=true&DIM_DATE=${encodeURIComponent(time)}&WIDTH=256`,
    ),
    features: [
      {
        properties: { folder: "/0/0" },
        getWmsOffering: () => ({
          dimensions: [{ name: "DATE", units: "ISO8601", values: "2026-01-01,2026-01-02" }],
        }),
      },
    ] as unknown as OptimizedUrlsMap["features"],
    operations: [
      { code: "GetMap", method: "GET", href: "https://example.org/wms" },
    ],
  });
  state.maps = [withDate("2026-01-01")];
  const { rerender } = render(<WebMapServiceControl />);
  const before = screen.getByTestId("image-url");

  state.maps = [withDate("2026-01-02")];
  rerender(
    <QueryClientProvider client={new QueryClient()}>
      <WebMapServiceControl />
    </QueryClientProvider>,
  );

  // the timeline of such a layer selects through DIM_DATE: the changing value must not remount
  // the overlay, which is what lets it keep drawing until the new frame has arrived (#705)
  expect(screen.getByTestId("image-url")).toBe(before);
  expect(before.textContent).toContain("DIM_DATE=2026-01-02");
});

test("a changed viewport answers with a fresh overlay instead of a stretched frame", () => {
  vi.useFakeTimers();
  state.maps = [batch("LAYERS=a&TIME=2026-01-01T00%3A00%3A00Z")];
  render(<WebMapServiceControl />);
  const before = screen.getByTestId("image-url");

  state.bounds = latLngBounds([5, 5], [15, 15]);
  act(() => state.viewportHandlers.forEach((handler) => handler()));
  act(() => vi.advanceTimersByTime(300));

  const after = screen.getByTestId("image-url");
  expect(after).not.toBe(before);
  expect(new URL(after.textContent!).searchParams.get("BBOX")).toBe(
    "5,5,15,15",
  );
});

test("a change in authentication answers with a fresh overlay whose time stays stable", () => {
  state.maps = [batch("LAYERS=a")];
  const { rerender } = render(<WebMapServiceControl />);
  const before = screen.getByTestId("image-url");

  state.context = {
    authenticationHeaders: [
      {
        id: "map",
        type: "header",
        origin: "https://example.org",
        name: "Authorization",
        value: "Basic secret",
      },
    ],
  } as typeof state.context;
  state.maps = [batch("LAYERS=a&TIME=2026-01-01T00%3A00%3A00Z")];
  state.maps[0].operations[0]["x-authentication-id"] = "map";
  rerender(
    <QueryClientProvider client={new QueryClient()}>
      <WebMapServiceControl />
    </QueryClientProvider>,
  );
  // frames are never reused across authentication contexts
  const authenticated = screen.getByTestId("image-url");
  expect(authenticated).not.toBe(before);

  // within the new authentication the same exemption for the selected time holds
  state.maps = [batch("LAYERS=a&TIME=2026-01-01T00%3A05%3A00Z")];
  state.maps[0].operations[0]["x-authentication-id"] = "map";
  rerender(
    <QueryClientProvider client={new QueryClient()}>
      <WebMapServiceControl />
    </QueryClientProvider>,
  );
  expect(screen.getByTestId("image-url")).toBe(authenticated);
});

test("identify asks the frame the map shows while a newer time is still on its way", async () => {
  // both layers were advanced to the newer observation...
  const selected = "2026-01-01T00:05:00Z";
  state.info = [
    {
      url: new URL(
        `https://example.org/wms?VERSION=1.3.0&LAYERS=water&QUERY_LAYERS=water&TIME=${encodeURIComponent(selected)}`,
      ),
      features: [
        { properties: { folder: "/0/0" }, getWmsOffering: () => undefined },
      ] as unknown as OptimizedUrlsMap["features"],
      operations: [
        { code: "GetFeatureInfo", method: "GET", href: "https://example.org/wms" },
      ],
    },
    {
      url: new URL(
        `https://example.org/wms?VERSION=1.3.0&LAYERS=roads&QUERY_LAYERS=roads&TIME=${encodeURIComponent(selected)}`,
      ),
      features: [
        { properties: { folder: "/0/1" }, getWmsOffering: () => undefined },
      ] as unknown as OptimizedUrlsMap["features"],
      operations: [
        { code: "GetFeatureInfo", method: "GET", href: "https://example.org/wms" },
      ],
    },
  ];
  // ...while the map of the water layer still draws the earlier observation
  state.displayedTimes["/0/0"] = "2026-01-01T00:00:00Z";
  const fetched = vi.fn().mockResolvedValue({
    ok: true,
    text: async () => "feature",
    headers: new Headers({ "content-type": "text/plain" }),
  });
  vi.stubGlobal("fetch", fetched);
  render(<WebMapServiceControl />);
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );
  await waitFor(() => expect(fetched).toHaveBeenCalledTimes(2));

  const times = Object.fromEntries(
    fetched.mock.calls.map(([url]) => {
      const params = new URL(url).searchParams;
      return [params.get("QUERY_LAYERS"), params.get("TIME")];
    }),
  );
  // features answer for the observation on the map; a layer whose image already shows the
  // selected time keeps being asked for that time
  expect(times).toEqual({
    water: "2026-01-01T00:00:00Z",
    roads: "2026-01-01T00:05:00Z",
  });
});

test("identify of a drawn server-default image asks the default although a time is selected", async () => {
  // the layer was advanced to an observation...
  state.info = [
    {
      url: new URL(
        "https://example.org/wms?VERSION=1.3.0&LAYERS=water&QUERY_LAYERS=water&TIME=2026-01-01T00%3A05%3A00Z",
      ),
      features: [
        { properties: { folder: "/0/0" }, getWmsOffering: () => undefined },
      ] as unknown as OptimizedUrlsMap["features"],
      operations: [
        { code: "GetFeatureInfo", method: "GET", href: "https://example.org/wms" },
      ],
    },
  ];
  // ...while the map still draws the server-default image, which carries no time
  state.displayedTimes["/0/0"] = "";
  const fetched = vi.fn().mockResolvedValue({
    ok: true,
    text: async () => "feature",
    headers: new Headers({ "content-type": "text/plain" }),
  });
  vi.stubGlobal("fetch", fetched);
  render(<WebMapServiceControl />);
  act(() =>
    state.onContextMenu?.({
      latlng: latLng(5, 5),
      containerPoint: point(20, 30),
    }),
  );
  await waitFor(() => expect(fetched).toHaveBeenCalledTimes(1));

  // features answer for the drawn default: the request carries no time at all
  expect(new URL(fetched.mock.calls[0][0]).searchParams.get("TIME")).toBeNull();
});
