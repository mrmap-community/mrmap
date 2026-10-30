import type { OWSResource } from "../../ows-lib/OwsContext/core";
import type { OfferingDimension } from "../../ows-lib/OwsContext/types";

import type { PropsWithChildren } from "react";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthOptions, remoteImageKey, remoteImageQuery } from "./remoteImage";
import { useTimeFrameBuffer } from "./useTimeFrameBuffer";

// the layer the request draws and the viewer session around it, as the buffering reads them
const state = vi.hoisted(() => ({
  animation: undefined as undefined | { folder: string; fps: number; loop: boolean },
  dimensions: [] as OfferingDimension[],
  timelines: {} as Record<string, number>,
}));
vi.mock("../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  useOwsContextBase: () => ({
    owsContext: {
      findResourceByFolder: (folder: string) => folder === "/0/0"
        ? { getWmsOffering: () => ({ dimensions: state.dimensions }) }
        : undefined,
    },
  }),
}));
vi.mock("../MapViewer/MapViewerBase", () => ({
  useMapViewerBase: () => ({ animation: state.animation, timelines: state.timelines }),
}));
vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
}));

const BASE = "https://example.test/wms?SERVICE=WMS&REQUEST=GetMap&LAYERS=radar&WIDTH=800";
/** six advertised observations, one every five minutes */
const TIMES = [
  "2026-01-01T00:00:00Z",
  "2026-01-01T00:05:00Z",
  "2026-01-01T00:10:00Z",
  "2026-01-01T00:15:00Z",
  "2026-01-01T00:20:00Z",
  "2026-01-01T00:25:00Z",
];
/** the request of one advertised frame */
const frame = (time: string) => `${BASE}&TIME=${encodeURIComponent(time)}`;
const AUTH = { headers: { Authorization: "first" } };
const features = [{ properties: { folder: "/0/0" } }] as unknown as OWSResource[];

let client: QueryClient;
let calls: { time: string | null; headers?: Record<string, string>; signal: AbortSignal }[];

/** the key a frame is kept under, built exactly as the overlay and the buffering build it */
const keyOf = (time: string, auth = AUTH) => remoteImageKey(frame(time), auth);
const requested = () => calls.map(call => call.time);
const askedFor = (time: string) => calls.filter(call => call.time === time).length;
/** every image the browser was asked for, besides the frame the overlay itself waits for */
const bufferedAround = (selection: string) =>
  [...new Set(requested().filter(time => time !== selection))];

/**
 * Answers every map request with an image; frames named by `refuse` are refused by the service and frames
 * named by `hold` never answer, which is how a request on its way is observed.
 */
const stubNetwork = ({ refuse = [], hold = [] }: { refuse?: string[]; hold?: string[] } = {}) => {
  vi.stubGlobal("fetch", vi.fn(async (href: string | URL, init?: RequestInit) => {
    const time = new URL(String(href)).searchParams.get("TIME");
    calls.push({
      time,
      headers: init?.headers as Record<string, string> | undefined,
      signal: (init?.signal ?? new AbortController().signal) as AbortSignal,
    });
    if (hold.includes(String(time))) return new Promise<Response>(() => undefined);
    if (refuse.includes(String(time)))
      return { ok: false, status: 503, statusText: "Service Unavailable" } as Response;
    return {
      ok: true,
      blob: async () => new Blob([`\x89PNG ${time}`], { type: "image/png" }),
    } as Response;
  }));
};

/** what an overlay of a time-enabled layer asks of the buffer: its own frame and the neighbouring ones */
const timeLayer = ({ time, auth = AUTH }: { time?: string; auth?: AuthOptions }) => {
  const url = new URL(time === undefined ? BASE : frame(time));
  useTimeFrameBuffer({ url, features, authOptions: auth });
  return useQuery(remoteImageQuery(url.href, auth, key => key));
};
const render = (initial: { time?: string; auth?: AuthOptions }) => renderHook(timeLayer, {
  initialProps: initial,
  wrapper: ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  ),
});

beforeEach(() => {
  client = new QueryClient();
  calls = [];
  state.animation = undefined;
  // the timeline of the layer is open in the viewer, which is what its frames are buffered for
  state.timelines = { "/0/0": 1 };
  state.dimensions = [{
    name: "time", units: "ISO8601", values: TIMES.join(","), default: TIMES[0],
  }];
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the frames buffered around a selection", () => {
  it("fetches the images of the frames which follow the selection", async () => {
    stubNetwork();

    render({ time: TIMES[1] });

    // two ahead and the one behind, which is what scrubbing reaches for before the next step
    await waitFor(() => expect(askedFor(TIMES[4])).toBe(1));
    expect([...new Set(requested())].sort())
      .toEqual([TIMES[0], TIMES[1], TIMES[2], TIMES[3], TIMES[4]].sort());
    expect(askedFor(TIMES[5])).toBe(0);
  });

  it("answers a frame which is already buffered without asking the service again", async () => {
    stubNetwork();
    const { rerender, result } = render({ time: TIMES[3] });
    await waitFor(() => expect(askedFor(TIMES[2])).toBe(1));

    // the viewer scrubs back onto the buffered frame
    rerender({ time: TIMES[2] });

    await waitFor(() => expect(result.current.data).toBeInstanceOf(Blob));
    expect(askedFor(TIMES[2])).toBe(1);
    expect(await result.current.data?.text()).toBe("\x89PNG 2026-01-01T00:10:00Z");
  });

  it("walks onwards only while the layer plays, returning to the first observation where it loops", async () => {
    state.animation = { folder: "/0/0", fps: 4, loop: true };
    stubNetwork();

    render({ time: TIMES[4] });

    await waitFor(() => expect(askedFor(TIMES[1])).toBe(1));
    expect(bufferedAround(TIMES[4]).sort()).toEqual([TIMES[0], TIMES[1], TIMES[5]].sort());
    // the frame behind the selection is no future of an animation
    expect(askedFor(TIMES[3])).toBe(0);
  });

  it("buffers nothing beyond the end of a range which does not loop", async () => {
    stubNetwork();

    render({ time: TIMES[5] });

    await waitFor(() => expect(askedFor(TIMES[4])).toBe(1));
    expect([...new Set(requested())].sort()).toEqual([TIMES[4], TIMES[5]].sort());
  });

  it("takes back the frames the selection moved away from, aborting those still on their way", async () => {
    stubNetwork({ hold: [TIMES[3]] });
    const { rerender } = render({ time: TIMES[0] });
    await waitFor(() => expect(askedFor(TIMES[2])).toBe(1));
    await waitFor(() => expect(askedFor(TIMES[3])).toBe(1));
    const onTheWay = calls.find(call => call.time === TIMES[3])!;

    // the viewer jumps to the end of the range: everything near the old selection is obsolete
    rerender({ time: TIMES[5] });

    await waitFor(() => expect(askedFor(TIMES[4])).toBe(1));
    expect(onTheWay.signal.aborted).toBe(true);
    for (const abandoned of [TIMES[1], TIMES[2], TIMES[3]])
      expect(client.getQueryData(keyOf(abandoned))).toBeUndefined();
  });

  it("asks the service again about a frame it refused instead of holding the refusal", async () => {
    stubNetwork({ refuse: [TIMES[1]] });
    const { rerender, result } = render({ time: TIMES[0] });
    await waitFor(() => expect(askedFor(TIMES[1])).toBe(1));

    // a frame the service refused is no buffer
    expect(client.getQueryData(keyOf(TIMES[1]))).toBeUndefined();

    rerender({ time: TIMES[1] });

    await waitFor(() => expect(askedFor(TIMES[1])).toBe(2));
    expect(result.current.error).toBeInstanceOf(Error);
  });

  it("keeps at most two buffered frames on their way at once", async () => {
    stubNetwork({ hold: TIMES.slice(1) });

    render({ time: TIMES[0] });

    await waitFor(() => expect(askedFor(TIMES[1])).toBe(1));
    await waitFor(() => expect(askedFor(TIMES[2])).toBe(1));
    // the third frame waits for a free slot rather than joining the queue
    expect(askedFor(TIMES[3])).toBe(0);
  });

  it("uses the slot a finished frame leaves free while another is still on its way", async () => {
    // one frame never answers, so only a free worker can bring the last one onto the map
    stubNetwork({ hold: [TIMES[1]] });

    render({ time: TIMES[0] });

    await waitFor(() => expect(askedFor(TIMES[3])).toBe(1));
    expect([...new Set(requested())].sort())
      .toEqual([TIMES[0], TIMES[1], TIMES[2], TIMES[3]].sort());
  });

  it("buffers nothing for times the service does not advertise", async () => {
    stubNetwork();
    state.dimensions = [{
      name: "time",
      units: "ISO8601",
      values: `${TIMES[0]}/${TIMES[5]}`, // a continuous range advertises no steps to buffer
    }];

    render({ time: TIMES[1] });

    await waitFor(() => expect(askedFor(TIMES[1])).toBe(1));
    expect(requested()).toEqual([TIMES[1]]);
  });

  it("buffers nothing for an exact time between the advertised observations", async () => {
    stubNetwork();

    render({ time: "2026-01-01T00:02:00Z" });

    await waitFor(() => expect(askedFor("2026-01-01T00:02:00Z")).toBe(1));
    expect(requested()).toEqual(["2026-01-01T00:02:00Z"]);
  });

  it("buffers nothing for a layer whose timeline the viewer does not work with", async () => {
    state.timelines = {};
    stubNetwork();

    render({ time: TIMES[0] });

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(requested()).toEqual([TIMES[0]]);
  });

  it("buffers the frames of the layer which plays, wherever its timeline sits", async () => {
    state.timelines = {};
    state.animation = { folder: "/0/0", fps: 2, loop: false };
    stubNetwork();

    render({ time: TIMES[0] });

    await waitFor(() => expect(askedFor(TIMES[2])).toBe(1));
    expect(bufferedAround(TIMES[0]).sort()).toEqual([TIMES[1], TIMES[2], TIMES[3]].sort());
  });

  it("buffers nothing for the image of the server default", async () => {
    stubNetwork();

    render({});

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(requested()).toEqual([null]);
  });

  it("keeps the frames of one authentication from answering another", async () => {
    const other = { headers: { Authorization: "second" } };
    stubNetwork();
    const { rerender } = render({ time: TIMES[0] });
    await waitFor(() => expect(askedFor(TIMES[2])).toBe(1));

    // the credential assignment of the layer changes: its frames belong to the old one
    rerender({ time: TIMES[0], auth: other });

    await waitFor(() => expect(
      calls.some(call => call.time === TIMES[1] && call.headers?.Authorization === "second"),
    ).toBe(true));
    expect(client.getQueryData(keyOf(TIMES[1]))).toBeUndefined();
    expect(client.getQueryData(keyOf(TIMES[1], other))).toBeInstanceOf(Blob);
  });

  it("releases every buffered frame when the overlay leaves the map", async () => {
    stubNetwork();
    const { unmount } = render({ time: TIMES[0] });
    await waitFor(() => expect(askedFor(TIMES[3])).toBe(1));

    unmount();

    for (const released of TIMES.slice(0, 4))
      expect(client.getQueryData(keyOf(released))).toBeUndefined();
  });
});
