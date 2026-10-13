import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { type PropsWithChildren } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePreview } from "./usePreview";
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
afterEach(() => vi.useRealTimers());
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
});
