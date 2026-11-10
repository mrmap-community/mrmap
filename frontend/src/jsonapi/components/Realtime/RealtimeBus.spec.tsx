import { ReadyState } from "react-use-websocket";

import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RealtimeBus from "./RealtimeBus";

const state = vi.hoisted(() => ({
  authenticated: true,
  enabled: true,
  // literal 0 = ReadyState.CONNECTING: vi.hoisted runs before the imports,
  // so the enum itself may only be used below, not in here
  readyState: 0 as number,
  socket: {} as Record<string, unknown>,
  url: "" as string,
  options: undefined as
    | {
        shouldReconnect?: (event: CloseEvent) => boolean;
        reconnectAttempts?: number;
        reconnectInterval?: (attemptNumber: number) => number;
      }
    | undefined,
  attachRealtimeOnMessage: vi.fn(),
  setRealtimeIsReady: vi.fn(),
}));

vi.mock("react-admin", () => ({
  useAuthState: () => ({ authenticated: state.authenticated }),
  useDataProvider: () => ({
    attachRealtimeOnMessage: state.attachRealtimeOnMessage,
  }),
}));
vi.mock("../../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({
    setRealtimeIsReady: state.setRealtimeIsReady,
  }),
}));
vi.mock("../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: "tok123" }),
}));
vi.mock("react-use-websocket", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  default: (
    url: string,
    options: typeof state.options,
    enabled: boolean,
  ) => {
    state.url = url;
    state.options = options;
    state.enabled = enabled;
    return {
      readyState: state.readyState,
      getWebSocket: () => state.socket,
    };
  },
}));

beforeEach(() => {
  state.authenticated = true;
  state.readyState = ReadyState.CONNECTING;
  state.socket = {};
  state.url = "";
  state.options = undefined;
  state.enabled = true;
  vi.clearAllMocks();
});

describe("RealtimeBus", () => {
  it("connects an authenticated user to the default endpoint with its token", () => {
    render(<RealtimeBus />);
    expect(state.url).toBe("ws://localhost:8001/ws/default/?token=tok123");
  });

  it("reconnects every drop, bounded with a capped backoff", () => {
    render(<RealtimeBus />);
    expect(state.options?.shouldReconnect?.({} as CloseEvent)).toBe(true);
    expect(state.options?.reconnectAttempts).toBe(10);
    const intervals = [0, 1, 2, 3, 4, 9].map((attempt) =>
      state.options?.reconnectInterval?.(attempt),
    );
    expect(intervals).toEqual([1000, 2000, 4000, 8000, 10000, 10000]);
  });

  it("hands the new socket to the data provider when a connection opens", () => {
    // a reconnect lands here too: react-use-websocket only swaps the socket,
    // and the data provider replays the live subscriptions over it (see
    // dataProvider.spec.tsx)
    state.readyState = ReadyState.OPEN;
    render(<RealtimeBus />);
    expect(state.attachRealtimeOnMessage).toHaveBeenCalledWith(state.socket);
    expect(state.setRealtimeIsReady).toHaveBeenCalledWith(ReadyState.OPEN);
  });

  it("reports a closed connection so the surfaces fall back to polling", () => {
    // BackgroundActivityPanel polls while the bus is not OPEN - that fallback
    // is what keeps the activity visible when the websocket stays down
    state.readyState = ReadyState.CLOSED;
    render(<RealtimeBus />);
    expect(state.setRealtimeIsReady).toHaveBeenCalledWith(ReadyState.CLOSED);
    expect(state.attachRealtimeOnMessage).not.toHaveBeenCalled();
  });
});
