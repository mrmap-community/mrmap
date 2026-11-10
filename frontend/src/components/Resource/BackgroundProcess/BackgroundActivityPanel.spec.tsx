import type { AnchorHTMLAttributes, ReactNode } from "react";
import type { RaRecord } from "react-admin";
import { ReadyState } from "react-use-websocket";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BackgroundActivityPanel from "./BackgroundActivityPanel";

const state = vi.hoisted(() => ({
  data: [] as RaRecord[],
  isPending: false,
  error: null as Error | null,
  refetch: vi.fn(),
  queryOptions: undefined as
    | { refetchInterval?: number | false }
    | undefined,
  listProps: undefined as
    | {
        resource?: string;
        perPage?: number;
        sort?: { field: string; order: string };
      }
    | undefined,
}));
// ReadyState.OPEN ist 1, ReadyState.CONNECTING ist 0
const realtime = vi.hoisted(() => ({ ready: 1 }));
vi.mock("../../../context/HttpClientContext", () => ({
  useHttpClientContext: () => ({ realtimeIsReady: realtime.ready }),
}));
vi.mock("../../../jsonapi/components/Realtime/RealtimeListBase", () => ({
  default: ({
    children,
    queryOptions,
    ...props
  }: {
    children: ReactNode;
    queryOptions?: { refetchInterval?: number | false };
    resource?: string;
    perPage?: number;
    sort?: { field: string; order: string };
  }) => {
    state.queryOptions = queryOptions;
    state.listProps = props;
    return <>{children}</>;
  },
}));
vi.mock("react-admin", () => ({
  useListContext: () => state,
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
  state.queryOptions = undefined;
  state.listProps = undefined;
  realtime.ready = ReadyState.OPEN;
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
  it("polls only while the realtime bus is not connected", () => {
    const { rerender } = render(<BackgroundActivityPanel />);
    expect(state.queryOptions?.refetchInterval).toBe(false);

    realtime.ready = ReadyState.CONNECTING;
    rerender(<BackgroundActivityPanel />);
    expect(state.queryOptions?.refetchInterval).toBe(20000);
  });
  it("asks for the ten newest processes, bounded, while the bus floods", () => {
    // a thousand running processes may not make the panel render a thousand
    // rows: the server page is the bound and the transport is the flood -
    // the panel only ever shows the ten most recent (epic #1203 acceptance)
    render(<BackgroundActivityPanel />);
    expect(state.listProps).toMatchObject({
      resource: "BackgroundProcess",
      perPage: 10,
      sort: { field: "id", order: "DESC" },
    });

    state.data = Array.from({ length: 10 }, (_, index) => ({
      id: index + 1,
      status: "running",
      description: `process ${index + 1}`,
    }));
    openPanel();
    expect(screen.getAllByText(/^process \d+$/)).toHaveLength(10);
    expect(screen.getByText("backgroundActivity.recent")).toBeInTheDocument();
  });
  it("opens from the keyboard, announces its state and closes on Escape", () => {
    render(<BackgroundActivityPanel />);
    const trigger = screen.getByRole("button", {
      name: "backgroundActivity.title",
    });
    trigger.focus();
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog")).toHaveAccessibleName(
      "backgroundActivity.title",
    );

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
  it("caps the panel at the viewport and scrolls its list", () => {
    // on a phone the panel must not run past the screen and the long list
    // must scroll inside the panel - both are pure style bounds which live
    // in the injected styles of the rendered panel
    const { container } = render(<BackgroundActivityPanel />);
    openPanel();
    const styles = [...document.querySelectorAll("style")].map(
      (style) => style.textContent ?? "",
    );
    const css = styles.join("") + container.ownerDocument.documentElement.innerHTML;
    expect(css).toMatch(/max-width:\s*calc\(100vw\s*-\s*32px\)/);
    expect(css).toMatch(/max-height:\s*60vh/);
    expect(css).toMatch(/overflow-y:\s*auto/);
  });
});
