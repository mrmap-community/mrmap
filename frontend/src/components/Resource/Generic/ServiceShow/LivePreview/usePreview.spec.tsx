import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { type PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { identifyUrl, useIdentify, usePreview } from "./usePreview";
const state = vi.hoisted(() => ({
  request: vi.fn(),
  endpoint: "https://mrmap.test/preview",
}));
vi.mock("../../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "https://mrmap.test",
  useHttpClientContext: () => ({
    api: {
      getOperation: () => ({}),
      getAxiosConfigForOperation: (
        _: string,
        [params, , options]: [object, unknown, object],
      ) => ({ url: state.endpoint, params, ...options }),
      client: { request: state.request },
    },
  }),
}));
vi.mock("../../../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: "secret" }),
}));
const wrapper = ({ children }: PropsWithChildren) => (
  <QueryClientProvider
    client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
  >
    {children}
  </QueryClientProvider>
);
beforeEach(() => {
  vi.clearAllMocks();
  state.endpoint = "https://mrmap.test/preview";
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe("transient preview requests", () => {
  it("aborts obsolete selections and rejects late results", async () => {
    let finishOld: ((value: object) => void) | undefined;
    state.request.mockImplementation(({ params }) =>
      params.selection === "old"
        ? new Promise((resolve) => {
            finishOld = resolve;
          })
        : Promise.resolve({ data: { source: "new" } }),
    );
    const client = new QueryClient();
    const result = renderHook(
      ({ selection }) =>
        usePreview("WFS", "service", { selection, bbox: "0,0,4,8" }),
      {
        initialProps: { selection: "old" },
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );
    await waitFor(() => expect(state.request).toHaveBeenCalledOnce());
    const signal = state.request.mock.calls[0][0].signal;
    result.rerender({ selection: "new" });
    expect(signal.aborted).toBe(true);
    await waitFor(() => expect(result.result.current.data?.source).toBe("new"));
    await act(async () => {
      finishOld?.({ data: { source: "old" } });
    });
    expect(result.result.current.data?.source).toBe("new");
    result.unmount();
  });
  it("debounces rapid viewport changes and cancels on unmount", async () => {
    const client = new QueryClient();
    const hook = renderHook(
      ({ bbox }) => usePreview("WFS", "service", { selection: "roads", bbox }),
      {
        initialProps: { bbox: "0,0,4,8" },
        wrapper: ({ children }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );
    hook.rerender({ bbox: "0,0,8,8" });
    hook.unmount();
    expect(state.request).not.toHaveBeenCalled();
  });
  it("does not send MrMap credentials to an origin supplied by a schema", async () => {
    state.endpoint = "https://unrelated.test/preview";
    const hook = renderHook(
      () => usePreview("WFS", "service", { selection: "roads" }),
      { wrapper },
    );
    await waitFor(() => expect(hook.result.current.error?.code).toBe("denied"));
    expect(state.request).not.toHaveBeenCalled();
  });
  it("completes the generated identify url with the viewport and both pixel spellings", () => {
    const generated = (version: string) =>
      identifyUrl(
        {
          url: `/mrmap-proxy/wms/service?SERVICE=WMS&VERSION=${version}&REQUEST=GetFeatureInfo&LAYERS=roads&QUERY_LAYERS=roads&INFO_FORMAT=text%2Fplain`,
          infoFormat: "text/plain",
        },
        { bbox: "0,0,4,8", width: 600, height: 400 },
        300.4,
        200.6,
      );
    const version130 = generated("1.3.0").searchParams;
    // WMS 1.3.0 declares the bbox in the axis order of EPSG:4326.
    expect(version130.get("BBOX")).toBe("0,0,8,4");
    expect(version130.get("WIDTH")).toBe("600");
    expect(version130.get("HEIGHT")).toBe("400");
    expect(version130.get("I")).toBe("300");
    expect(version130.get("J")).toBe("201");
    expect(version130.get("INFO_FORMAT")).toBe("text/plain");
    // 1.1.1 always keeps the west,south,east,north order of the viewport.
    expect(generated("1.1.1").searchParams.get("BBOX")).toBe("0,0,4,8");
  });
  it("maps a proxy answer to a distinguishable identify failure", async () => {
    const link = {
      url: "/mrmap-proxy/wms/service?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetFeatureInfo&LAYERS=roads&QUERY_LAYERS=roads&INFO_FORMAT=text%2Fplain",
      infoFormat: "text/plain",
    };
    const exception =
      '<?xml version="1.0"?><ServiceExceptionReport version="1.1.1"><ServiceException code="LayerNotDefined">unknown layer</ServiceException></ServiceExceptionReport>';
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(exception, { headers: { "Content-Type": "application/xml" } }),
      ),
    );
    const hook = renderHook(
      () =>
        useIdentify(link, { bbox: "0,0,4,8", width: 600, height: 400 }, { x: 10, y: 20 }),
      { wrapper },
    );
    await waitFor(() => expect(hook.result.current.error?.code).toBe("ogc"), {
      timeout: 5000,
    });
    hook.unmount();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("no access", { status: 403 })),
    );
    const refused = renderHook(
      () =>
        useIdentify(link, { bbox: "0,0,4,8", width: 600, height: 400 }, { x: 10, y: 20 }),
      { wrapper },
    );
    await waitFor(() => expect(refused.result.current.error?.code).toBe("denied"), {
      timeout: 5000,
    });
    refused.unmount();
  });
});
