import { useDataProvider, useGetList } from "react-admin";

import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import useServiceAlerts from "./useServiceAlerts";

const state = vi.hoisted(() => ({
  /** the readiness of the realtime bus, ReadyState.CONNECTING is 0 */
  ready: 0,
}));

vi.mock("../../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ realtimeIsReady: state.ready }),
}));
vi.mock("react-admin", () => ({
  useDataProvider: vi.fn(),
  useGetList: vi.fn(),
}));
describe("useServiceAlerts", () => {
  it("polls and refetches scoped data on invalidation, then unsubscribes", () => {
    const provider = { subscribe: vi.fn(), unsubscribe: vi.fn() };
    const refetch = vi.fn();
    vi.mocked(useDataProvider).mockReturnValue(
      provider as unknown as ReturnType<typeof useDataProvider>,
    );
    vi.mocked(useGetList).mockReturnValue({ refetch } as unknown as ReturnType<
      typeof useGetList
    >);
    const { unmount } = renderHook(useServiceAlerts);
    expect(useGetList).toHaveBeenCalledWith(
      "ServiceAlert",
      expect.objectContaining({ pagination: { page: 1, perPage: 5 } }),
      // the hook only polls while the bus is not connected - it is DOWN here
      { refetchInterval: 20000, retry: false },
    );
    const [topic, callback] = provider.subscribe.mock.calls[0];
    expect(topic).toBe("resource/ServiceAlert");
    callback();
    expect(refetch).toHaveBeenCalledOnce();
    unmount();
    expect(provider.unsubscribe).toHaveBeenCalledWith(topic, callback);
  });

  it("leaves the polling to the bus once that is connected", () => {
    state.ready = 1; // ReadyState.OPEN
    const provider = { subscribe: vi.fn(), unsubscribe: vi.fn() };
    vi.mocked(useDataProvider).mockReturnValue(
      provider as unknown as ReturnType<typeof useDataProvider>,
    );
    vi.mocked(useGetList).mockReturnValue({ refetch: vi.fn() } as unknown as ReturnType<
      typeof useGetList
    >);
    renderHook(useServiceAlerts);
    expect(useGetList).toHaveBeenCalledWith(
      "ServiceAlert",
      expect.objectContaining({ pagination: { page: 1, perPage: 5 } }),
      { refetchInterval: false, retry: false },
    );
    // the invalidation subscription stays - it is the live authority
    expect(provider.subscribe).toHaveBeenCalledWith(
      "resource/ServiceAlert",
      expect.any(Function),
    );
  });
});
