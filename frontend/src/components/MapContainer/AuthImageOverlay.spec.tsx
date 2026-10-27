import { render } from "@testing-library/react";
import { latLngBounds } from "leaflet";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthImageOverlay } from "./AuthImageOverlay";

const query = vi.hoisted(() => ({
  run: undefined as
    undefined | ((context: { signal: AbortSignal }) => Promise<Blob>),
  data: undefined as undefined | Blob,
}));
// every overlay the component draws, with what it was given and the calls made on it
const overlays = vi.hoisted(() => [] as {
  opacity?: number;
  url?: string;
  eventHandlers?: { load?: () => void; error?: () => void };
  drawn: { setOpacity: ReturnType<typeof vi.fn> };
}[]);
// what the component reports about the picture it draws to the status of the map
const loading = vi.hoisted(() => ({
  report: vi.fn(),
  remove: vi.fn(),
}));
vi.mock("@tanstack/react-query", () => ({
  useQuery: ({
    queryFn,
    enabled = true,
  }: {
    queryFn: typeof query.run;
    enabled?: boolean;
  }) => {
    query.run = enabled ? queryFn : undefined;
    return enabled
      ? {
          data: query.data,
          isFetching: query.data === undefined,
          error: undefined,
        }
      : { data: undefined, isFetching: false, error: undefined };
  },
}));
vi.mock("react-leaflet", () => ({
  ImageOverlay: ({
    opacity,
    url,
    eventHandlers,
    ref,
  }: {
    opacity?: number;
    url?: string;
    eventHandlers?: { load?: () => void; error?: () => void };
    ref?: ((layer: unknown) => void) | { current: unknown } | null;
  }) => {
    // the overlay leaflet answers with through the ref, keeping the calls made on it
    const drawn = { setOpacity: vi.fn() };
    overlays.push({ opacity, url, eventHandlers, drawn });
    if (typeof ref === "function") ref(drawn);
    else if (ref !== null && ref !== undefined) ref.current = drawn;
    return null;
  },
}));
vi.mock("../MapViewer/MapViewerBase", () => ({
  useMapViewerBase: () => ({
    reportMapLoading: loading.report,
    removeMapLoading: loading.remove,
  }),
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
    query.data = new Blob(["\x89PNG"], { type: "image/png" });
    overlays.length = 0;
  };
  afterEach(() => {
    query.data = undefined;
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

describe("the picture of a remote service which asks for nothing", () => {
  const remote = "https://remote.test/wms?REQUEST=GetMap";
  it("is drawn from its own url instead of being fetched across the origin", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    overlays.length = 0;
    render(
      <AuthImageOverlay
        bounds={latLngBounds([0, 0], [1, 1])}
        optimiuedUrl={{ url: new URL(remote), features: [], operations: [] }}
      />,
    );
    expect(fetch).not.toHaveBeenCalled();
    expect(overlays.at(-1)?.url).toBe(remote);
    // what the browser reports about the picture is what the map states about itself
    overlays.at(-1)?.eventHandlers?.load?.();
    expect(loading.report).toHaveBeenCalledWith(
      `image:${remote}`,
      "ready",
      undefined,
      expect.any(Number),
    );
    overlays.at(-1)?.eventHandlers?.error?.();
    expect(loading.report).toHaveBeenCalledWith(
      `image:${remote}`,
      "error",
      { message: "viewerMap.imageFailed", features: [] },
      expect.any(Number),
    );
  });
});
