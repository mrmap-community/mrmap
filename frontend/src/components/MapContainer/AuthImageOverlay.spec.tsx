import { render } from "@testing-library/react";
import { latLngBounds } from "leaflet";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthImageOverlay } from "./AuthImageOverlay";

const query = vi.hoisted(() => ({
  run: undefined as
    undefined | ((context: { signal: AbortSignal }) => Promise<Blob>),
  data: undefined as undefined | Blob,
}));
// every overlay the component draws, with the blending it was given and the calls made on it
const overlays = vi.hoisted(() => [] as {
  opacity?: number;
  drawn: { setOpacity: ReturnType<typeof vi.fn> };
}[]);
vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryFn }: { queryFn: typeof query.run }) => {
    query.run = queryFn;
    return {
      data: query.data,
      isFetching: query.data === undefined,
      error: undefined,
    };
  },
}));
vi.mock("react-leaflet", () => ({
  ImageOverlay: ({
    opacity,
    ref,
  }: {
    opacity?: number;
    ref?: ((layer: unknown) => void) | { current: unknown } | null;
  }) => {
    // the overlay leaflet answers with through the ref, keeping the calls made on it
    const drawn = { setOpacity: vi.fn() };
    overlays.push({ opacity, drawn });
    if (typeof ref === "function") ref(drawn);
    else if (ref !== null && ref !== undefined) ref.current = drawn;
    return null;
  },
}));
vi.mock("../MapViewer/MapViewerBase", () => ({
  useMapViewerBase: () => ({
    reportMapLoading: vi.fn(),
    removeMapLoading: vi.fn(),
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
