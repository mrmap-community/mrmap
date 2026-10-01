import { render } from "@testing-library/react";
import { latLngBounds } from "leaflet";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthImageOverlay } from "./AuthImageOverlay";

const query = vi.hoisted(() => ({
  run: undefined as
    undefined | ((context: { signal: AbortSignal }) => Promise<Blob>),
}));
vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryFn }: { queryFn: typeof query.run }) => {
    query.run = queryFn;
    return { data: undefined, isFetching: true, error: undefined };
  },
}));
vi.mock("react-leaflet", () => ({ ImageOverlay: () => null }));
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
const prepare = (blob: ReturnType<typeof makeBlob>) => {
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
      expect.objectContaining({ signal, headers: { Authorization: "test" } }),
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
