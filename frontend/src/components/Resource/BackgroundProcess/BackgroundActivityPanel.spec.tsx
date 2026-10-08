import { act, fireEvent, render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import type { RaRecord } from "react-admin";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BackgroundActivityPanel from "./BackgroundActivityPanel";

const state = vi.hoisted(() => ({
  data: [] as RaRecord[],
  isPending: false,
  error: null as Error | null,
  refetch: vi.fn(),
  callbacks: new Set<() => void>(),
  unsubscribe: vi.fn(),
}));
const provider = {
  subscribe: (_topic: string, callback: () => void) =>
    state.callbacks.add(callback),
  unsubscribe: (_topic: string, callback: () => void) => {
    state.callbacks.delete(callback);
    state.unsubscribe();
  },
};
vi.mock("../../../jsonapi/components/Realtime/RealtimeListBase", () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("react-admin", () => ({
  useListContext: () => state,
  useDataProvider: () => provider,
  useTranslate: () => (key: string, options?: Record<string, unknown>) =>
    key === "backgroundActivity.steps"
      ? `${options?.done} of ${options?.total} steps`
      : key,
  useCreatePath:
    () =>
    ({ type, id }: { type: string; id?: number }) =>
      type === "show" ? `/BackgroundProcess/${id}/show` : "/BackgroundProcess",
  Link: ({
    to,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) => (
    <a href={to} {...props} />
  ),
}));
beforeEach(() => {
  state.data = [];
  state.isPending = false;
  state.error = null;
  state.callbacks.clear();
  vi.clearAllMocks();
});
afterEach(() => vi.useRealTimers());
const openPanel = () =>
  fireEvent.click(
    screen.getByRole("button", { name: "backgroundActivity.title" }),
  );

describe("BackgroundActivityPanel", () => {
  it("shows progress, zero completed steps, and detail links", () => {
    state.data = [
      {
        id: 12,
        description: "Register weather service",
        phase: "Collecting metadata",
        status: "running",
        doneSteps: 0,
        totalSteps: 6,
        progress: 0,
      },
    ];
    render(<BackgroundActivityPanel />);
    openPanel();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Register weather service")).toBeInTheDocument();
    expect(screen.getByText("Collecting metadata")).toBeInTheDocument();
    expect(screen.getByText("0 of 6 steps")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "0",
    );
    expect(
      screen.getByRole("link", { name: "backgroundActivity.viewDetails" }),
    ).toHaveAttribute("href", "/BackgroundProcess/12/show");
    expect(
      screen.getByRole("link", { name: "backgroundActivity.viewAll" }),
    ).toHaveAttribute("href", "/BackgroundProcess");
  });
  it("uses indeterminate progress when the total is unknown", () => {
    state.data = [
      {
        id: 1,
        status: "running",
        phase: "Discovering records",
        totalSteps: null,
      },
    ];
    render(<BackgroundActivityPanel />);
    openPanel();
    expect(screen.getByRole("progressbar")).not.toHaveAttribute(
      "aria-valuenow",
    );
  });
  it("shows empty and failed states", () => {
    const { rerender } = render(<BackgroundActivityPanel />);
    openPanel();
    expect(screen.getByText("backgroundActivity.empty")).toBeInTheDocument();
    state.data = [
      {
        id: 2,
        status: "failed",
        description: "Monitoring",
        phase: "Connection timed out",
      },
    ];
    rerender(<BackgroundActivityPanel />);
    expect(
      screen.getByText("backgroundActivity.status.failed"),
    ).toBeInTheDocument();
    expect(screen.getByText("Connection timed out")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
  it("shows load errors and lets the user retry", () => {
    state.error = new Error("Unavailable");
    render(<BackgroundActivityPanel />);
    openPanel();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "backgroundActivity.loadError",
    );
    fireEvent.click(screen.getByRole("button", { name: "ra.action.refresh" }));
    expect(state.refetch).toHaveBeenCalledOnce();
  });
  it("coalesces realtime events and cleans up its subscription and pending refresh", () => {
    vi.useFakeTimers();
    const { unmount } = render(<BackgroundActivityPanel />);
    act(() => {
      state.callbacks.forEach((callback) => {
        callback();
        callback();
      });
      vi.advanceTimersByTime(1000);
    });
    expect(state.refetch).toHaveBeenCalledOnce();
    act(() => state.callbacks.forEach((callback) => callback()));
    unmount();
    act(() => vi.advanceTimersByTime(1000));
    expect(state.refetch).toHaveBeenCalledOnce();
    expect(state.unsubscribe).toHaveBeenCalledOnce();
    expect(state.callbacks.size).toBe(0);
  });
});
