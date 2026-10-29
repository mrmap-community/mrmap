import type { OWSResource } from "../../ows-lib/OwsContext/core";

import { act, render } from "@testing-library/react";
import { latLngBounds } from "leaflet";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthImageOverlay } from "./AuthImageOverlay";

const query = vi.hoisted(() => ({
  run: undefined as
    undefined | ((context: { signal: AbortSignal }) => Promise<Blob>),
  state: {
    data: undefined as undefined | Blob,
    isFetching: true,
    error: undefined as undefined | Error,
  },
}));
// every overlay the component draws, with the image and blending it was given and the calls
// made on it
const overlays = vi.hoisted(() => [] as {
  url?: string;
  opacity?: number;
  drawn: {
    setOpacity: ReturnType<typeof vi.fn>;
    setUrl: ReturnType<typeof vi.fn>;
  };
}[]);
// the viewer context the overlay reports through, shared so specs can inspect the reports
const viewer = vi.hoisted(() => ({
  reportMapLoading: vi.fn(),
  removeMapLoading: vi.fn(),
  setDisplayedTime: vi.fn(),
}));
vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryFn }: { queryFn: typeof query.run }) => {
    query.run = queryFn;
    return query.state;
  },
}));
vi.mock("react-leaflet", () => ({
  ImageOverlay: ({
    opacity,
    url,
    ref,
  }: {
    opacity?: number;
    url?: string;
    ref?: ((layer: unknown) => void) | { current: unknown } | null;
  }) => {
    // the overlay leaflet answers with through the ref, keeping the calls made on it
    const drawn = { setOpacity: vi.fn(), setUrl: vi.fn() };
    overlays.push({ opacity, url, drawn });
    if (typeof ref === "function") ref(drawn);
    else if (ref !== null && ref !== undefined) ref.current = drawn;
    return null;
  },
}));
vi.mock("../MapViewer/MapViewerBase", () => ({
  useMapViewerBase: () => viewer,
}));
afterEach(() => vi.unstubAllGlobals());
const makeBlob = (parts: string[], { type }: { type: string }) => ({
  type,
  text: vi.fn(async () => parts.join("")),
  slice: vi.fn((start: number, end: number) => ({
    text: async () => parts.join("").slice(start, end),
  })),
});
const prepare = (blob: ReturnType<typeof makeBlob>, authenticationError?: string) => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, blob: async () => blob });
  vi.stubGlobal("fetch", fetch);
  render(
    <AuthImageOverlay
      bounds={latLngBounds([0, 0], [1, 1])}
      optimiuedUrl={{
        url: new URL("https://example.test/wms"),
        features: [],
        operations: [],
      }}
      authenticationError={authenticationError}
      auth={{ headers: { Authorization: "test" } }}
    />,
  );
  return fetch;
};
describe("map image requests", () => {
  it("does not decode a complete binary image and forwards authentication and cancellation", async () => {
    const blob = makeBlob(["\x89PNG" + "x".repeat(10000)], {
      type: "image/png",
    });
    const readWholeBlob = vi.spyOn(blob, "text");
    const fetch = prepare(blob);
    const signal = new AbortController().signal;
    expect(await query.run!({ signal })).toBe(blob);
    expect(readWholeBlob).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledWith(
      "https://example.test/wms",
      expect.objectContaining({ signal, headers: { Authorization: "test" }, redirect: "error", credentials: "omit" }),
    );
  });
  it.each(["application/xml", "image/png"])(
    "recognizes XML service errors labelled as %s",
    async (type) => {
      prepare(
        makeBlob(
          [
            '  <ServiceExceptionReport><ServiceException code="LayerNotDefined">Missing layer</ServiceException></ServiceExceptionReport>',
          ],
          { type },
        ),
      );
      await expect(
        query.run!({ signal: new AbortController().signal }),
      ).rejects.toThrow("LayerNotDefined: Missing layer");
    },
  );
});

describe("the blending of a drawn image", () => {
  /** the image of a map request, drawn with the blending the viewer holds for its layers */
  const imageWithBlending = (opacity: number | undefined) => (
    <AuthImageOverlay
      bounds={latLngBounds([0, 0], [1, 1])}
      optimiuedUrl={{
        url: new URL("https://example.test/wms"),
        features: [],
        operations: [],
      }}
      opacity={opacity}
    />
  );

  /** lets the image of a layer arrive, so the overlay which draws it is mounted */
  const startBlending = () => {
    const BrowserURL = URL;
    vi.stubGlobal(
      "URL",
      class extends BrowserURL {
        static createObjectURL = vi.fn(() => "blob:map-image");
        static revokeObjectURL = vi.fn();
      },
    );
    query.state = {
      data: new Blob(["\x89PNG"], { type: "image/png" }),
      isFetching: false,
      error: undefined,
    };
    overlays.length = 0;
  };
  afterEach(() => {
    query.state = { data: undefined, isFetching: true, error: undefined };
  });

  it("draws the image with the blending of its layers and asks the overlay for it", () => {
    startBlending();

    render(imageWithBlending(0.25));

    expect(overlays.at(-1)?.opacity).toBe(0.25);
    // an overlay keeps the options it was created with, so the value goes to the overlay as well
    expect(overlays.at(-1)?.drawn.setOpacity).toHaveBeenCalledWith(0.25);
  });

  it("blends the image already drawn when the viewer changes the layer", () => {
    startBlending();
    const { rerender } = render(imageWithBlending(1));

    expect(overlays.at(-1)?.drawn.setOpacity).toHaveBeenCalledWith(1);

    rerender(imageWithBlending(0.4));

    expect(overlays.at(-1)?.opacity).toBe(0.4);
    expect(overlays.at(-1)?.drawn.setOpacity).toHaveBeenCalledWith(0.4);
  });
});

it("does not fetch a map when credentials are missing", async () => {
  const fetch = prepare(makeBlob(["image"], { type: "image/png" }), "missing");
  await expect(query.run!({ signal: new AbortController().signal })).rejects.toThrow();
  expect(fetch).not.toHaveBeenCalled();
});

describe("the frame the map keeps while time advances", () => {
  /** a time-enabled layer request; the folder lets the viewer address the drawn frame */
  const request = (time: string) => ({
    url: new URL(
      `https://example.test/wms?LAYERS=radar&TIME=${encodeURIComponent(time)}`,
    ),
    features: [
      { properties: { folder: "/0/0" } },
    ] as unknown as OWSResource[],
    operations: [],
  });
  const frame = (name: string) =>
    new Blob([`\x89PNG ${name}`], { type: "image/png" });

  /** names every object URL the browser hands out, so swaps and releases are traceable */
  const trackObjectUrls = () => {
    const BrowserURL = URL;
    let served = 0;
    vi.stubGlobal(
      "URL",
      class extends BrowserURL {
        static createObjectURL = vi.fn(() => `blob:frame-${++served}`);
        static revokeObjectURL = vi.fn();
      },
    );
  };
  beforeEach(() => {
    viewer.reportMapLoading.mockClear();
    viewer.setDisplayedTime.mockClear();
  });
  afterEach(() => {
    query.state = { data: undefined, isFetching: true, error: undefined };
  });

  it("keeps drawing the previous frame until the next one has arrived and releases it with the swap", () => {
    trackObjectUrls();
    query.state = { data: frame("first"), isFetching: false, error: undefined };
    const { rerender } = render(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:00:00Z")} />,
    );
    expect(overlays.at(-1)?.url).toBe("blob:frame-1");

    // the viewer selects the next time: the request runs while the drawn image stays
    query.state = { data: undefined, isFetching: true, error: undefined };
    rerender(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:05:00Z")} />,
    );
    expect(overlays.at(-1)?.url).toBe("blob:frame-1");

    // the answer arrives and takes the map in one swap, without a blank in between
    query.state = { data: frame("second"), isFetching: false, error: undefined };
    rerender(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:05:00Z")} />,
    );

    expect(overlays.at(-1)?.url).toBe("blob:frame-2");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:frame-1");
  });

  it("keeps the drawn frame while a failed request reports itself through the status", () => {
    trackObjectUrls();
    query.state = { data: frame("first"), isFetching: false, error: undefined };
    const { rerender } = render(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:00:00Z")} />,
    );

    query.state = { data: undefined, isFetching: false, error: new Error("HTTP 503: Service Unavailable") };
    rerender(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:05:00Z")} />,
    );

    expect(overlays.at(-1)?.url).toBe("blob:frame-1");
    expect(viewer.reportMapLoading).toHaveBeenCalledWith(
      "image:https://example.test/wms?LAYERS=radar&TIME=2026-01-01T00%3A05%3A00Z",
      "error",
      expect.objectContaining({ message: "HTTP 503: Service Unavailable" }),
      expect.any(Number),
    );
  });

  it("refuses an image the browser cannot decode and keeps drawing the last one", async () => {
    trackObjectUrls();
    query.state = { data: frame("first"), isFetching: false, error: undefined };
    const { rerender } = render(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:00:00Z")} />,
    );

    // the next answer carries bytes no browser will draw
    vi.stubGlobal("Image", class {
      src = "";
      decode = () => Promise.reject(new Error("broken image"));
    });
    query.state = { data: frame("garbage"), isFetching: false, error: undefined };
    rerender(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:05:00Z")} />,
    );
    await act(async () => undefined);

    expect(overlays.at(-1)?.url).toBe("blob:frame-1");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:frame-2");
    expect(viewer.reportMapLoading).toHaveBeenCalledWith(
      expect.any(String),
      "error",
      expect.objectContaining({ message: expect.stringContaining("viewerMap.undecodable") }),
      expect.any(Number),
    );
  });

  it("discards a frame whose request the newer selection replaced", async () => {
    trackObjectUrls();
    // the first frame displays after the browser decoded it
    let decodeFirst: () => void = () => undefined;
    vi.stubGlobal("Image", class {
      src = "";
      decode = () =>
        new Promise<void>((resolve) => {
          decodeFirst = resolve;
        });
    });
    query.state = { data: frame("first"), isFetching: false, error: undefined };
    const { rerender } = render(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:00:00Z")} />,
    );
    await act(async () => decodeFirst());
    expect(overlays.at(-1)?.url).toBe("blob:frame-1");

    // the viewer scrubs onward while the second frame is still decoding
    let decodeSecond: () => void = () => undefined;
    vi.stubGlobal("Image", class {
      src = "";
      decode = () =>
        new Promise<void>((resolve) => {
          decodeSecond = resolve;
        });
    });
    query.state = { data: frame("second"), isFetching: false, error: undefined };
    rerender(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:05:00Z")} />,
    );

    // an even newer selection invalidates that decoding frame before it could take the map
    query.state = { data: undefined, isFetching: true, error: undefined };
    rerender(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:10:00Z")} />,
    );
    await act(async () => decodeSecond());

    expect(overlays.at(-1)?.url).toBe("blob:frame-1");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:frame-2");
  });

  it("answers which observation the map shows and forgets it when the overlay leaves", () => {
    trackObjectUrls();
    query.state = { data: frame("first"), isFetching: false, error: undefined };
    const { unmount } = render(
      <AuthImageOverlay bounds={latLngBounds([0, 0], [1, 1])} optimiuedUrl={request("2026-01-01T00:00:00Z")} />,
    );

    expect(viewer.setDisplayedTime).toHaveBeenCalledWith("/0/0", "2026-01-01T00:00:00Z");

    unmount();

    expect(viewer.setDisplayedTime).toHaveBeenLastCalledWith("/0/0", undefined);
  });

  it("names the server default as the observation a time-less image answers for", () => {
    trackObjectUrls();
    query.state = { data: frame("default"), isFetching: false, error: undefined };
    render(
      <AuthImageOverlay
        bounds={latLngBounds([0, 0], [1, 1])}
        optimiuedUrl={{
          url: new URL("https://example.test/wms?LAYERS=radar"),
          features: [
            { properties: { folder: "/0/0" } },
          ] as unknown as OWSResource[],
          operations: [],
        }}
      />,
    );

    // an image without a time parameter answers the server default, not "nothing is drawn"
    expect(viewer.setDisplayedTime).toHaveBeenCalledWith("/0/0", "");
  });
});
