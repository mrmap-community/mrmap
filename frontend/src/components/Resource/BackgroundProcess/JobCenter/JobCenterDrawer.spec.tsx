import type { BackgroundJobRecord, JobStoreState } from "./jobStore";

import type { AnchorHTMLAttributes, ReactNode } from "react";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import JobCenterDrawer from "./JobCenterDrawer";

const state = vi.hoisted(() => ({
  open: true,
  setOpen: vi.fn(),
  clearCompleted: vi.fn(),
  store: { jobs: {} } as JobStoreState,
  countFilters: [] as Record<string, string>[],
  history: {
    data: [] as BackgroundJobRecord[],
    isPending: false,
    error: null as Error | null,
    refetch: vi.fn(),
  },
  realtimeProps: undefined as Record<string, unknown> | undefined,
}));

vi.mock("./BackgroundJobCenterContext", () => ({
  useBackgroundJobCenter: () => ({
    state: state.store,
    open: state.open,
    setOpen: state.setOpen,
    clearCompleted: state.clearCompleted,
  }),
}));

vi.mock("../../../../jsonapi/components/Count", () => ({
  Count: ({ filter }: { filter: Record<string, string> }) => {
    state.countFilters.push(filter);
    return <span>42</span>;
  },
}));

vi.mock("../../../../jsonapi/components/Realtime/RealtimeListBase", () => ({
  default: ({ children, ...props }: { children: ReactNode }) => {
    state.realtimeProps = props as Record<string, unknown>;
    return <>{children}</>;
  },
}));

vi.mock("../../../Field/RelativeDateField", () => ({
  default: ({ source }: { source: string }) => <span>{`date:${source}`}</span>,
}));

vi.mock("../../../Field/ProgressField", () => ({
  default: ({
    source,
    indeterminate,
  }: {
    source: string;
    indeterminate?: boolean;
  }) => (
    <div
      role="progressbar"
      data-source={source}
      data-indeterminate={String(indeterminate ?? false)}
    />
  ),
}));

vi.mock("../AbortBackgroundProcessButton", () => ({
  default: () => <button aria-label="backgroundActivity.abort" />,
}));

vi.mock("../ProcessStatusField", () => ({
  default: ({ source }: { source: string }) => (
    <span role="status">{`chip:${source}`}</span>
  ),
}));

vi.mock("react-admin", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  const RecordContext = React.createContext<
    Record<string, unknown> | undefined
  >(undefined);
  return {
    RecordContext,
    useRecordContext: () => React.useContext(RecordContext),
    useListContext: () => state.history,
    useTranslate: () => {
      // the stub knows one word of the phases table (#1267) to prove the
      // drawer looks the reported key up; every other key keeps answering
      // the `_` fallback or itself, as before
      const words: Record<string, string> = {
        "backgroundActivity.phases.collect_metadata_records":
          "Collect metadata records",
      };
      return (key: string, options?: Record<string, unknown>) =>
        words[key] ??
        (options !== undefined && options._ !== undefined
          ? String(options._)
          : key);
    },
    useCreatePath:
      () =>
      ({ type, id }: { type: string; id?: number | string }) =>
        type === "show"
          ? `/BackgroundProcess/${id}/show`
          : "/BackgroundProcess",
    Link: ({
      to,
      children,
      ...props
    }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) => (
      <a href={to} {...props}>
        {children}
      </a>
    ),
  };
});

const job = (overrides: Partial<BackgroundJobRecord>): BackgroundJobRecord => ({
  id: 1,
  status: "running",
  state: "running",
  processType: "harvest",
  dateCreated: "2026-11-10T10:00:00Z",
  ...overrides,
});

const storeOf = (records: BackgroundJobRecord[]): JobStoreState => ({
  jobs: Object.fromEntries(
    records.map((record) => [String(record.id), record]),
  ),
});

/** the visible tab panel: the other panels of the drawer answer with the
 *  `hidden` attribute and are excluded from `getByRole` by themselves */
const panel = () => within(screen.getByRole("tabpanel"));

beforeEach(() => {
  state.open = true;
  state.setOpen = vi.fn();
  state.clearCompleted = vi.fn();
  state.store = { jobs: {} };
  state.countFilters = [];
  state.history = {
    data: [],
    isPending: false,
    error: null,
    refetch: vi.fn(),
  };
  state.realtimeProps = undefined;
  vi.clearAllMocks();
});

describe("JobCenterDrawer", () => {
  it("renders nothing while closed and the shell while open", () => {
    state.open = false;
    const { rerender } = render(<JobCenterDrawer />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    state.open = true;
    rerender(<JobCenterDrawer />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("counts the tiles and the tabs through the collection endpoint", () => {
    render(<JobCenterDrawer />);
    // the tiles and the counted tab labels all read the api, not the store
    expect(state.countFilters).toContainEqual({ status: "running" });
    expect(state.countFilters).toContainEqual({ status: "pending" });
    expect(state.countFilters).toContainEqual({ status: "failed,aborted" });
    expect(
      state.countFilters.some((filter) => "doneAt_filter_lookup_gt" in filter),
    ).toBe(true);
    const runningTab = screen.getByRole("tab", { name: /tabs.running/ });
    expect(runningTab).toHaveTextContent("42");
  });

  it("groups the store's processes by their related resource", () => {
    state.store = storeOf([
      job({
        id: 1,
        description: "Register weather service",
        relatedResource: { type: "WebMapService", id: "12345678-9abc" },
      }),
      job({
        id: 2,
        description: "Harvest counties",
        relatedResource: { type: "WebMapService", id: "12345678-9abc" },
      }),
      job({ id: 3, description: "Index everything", processType: "indexer" }),
    ]);
    render(<JobCenterDrawer />);
    const rows = panel();
    expect(rows.getByText("Register weather service")).toBeInTheDocument();
    expect(rows.getByText("Harvest counties")).toBeInTheDocument();
    expect(rows.getByText("WebMapService · 12345678")).toBeInTheDocument();
    // without a related resource the process type names the group
    expect(rows.getByText("Index everything")).toBeInTheDocument();
    expect(rows.getAllByText("indexer").length).toBeGreaterThanOrEqual(2);
  });

  it("translates a reported phase key and answers a raw report as written", () => {
    // the registration reports its phases as keys (#1267); what is no key -
    // the error text a task reported into the phase - stays readable
    state.store = storeOf([
      job({
        id: 4,
        description: "Register weather service",
        phase: "collect_metadata_records",
      }),
      job({
        id: 5,
        description: "Broken registration",
        phase: "the capabilities document is broken",
      }),
    ]);
    render(<JobCenterDrawer />);
    const rows = panel();
    expect(
      rows.getByText("harvest · Collect metadata records"),
    ).toBeInTheDocument();
    expect(
      rows.getByText("harvest · the capabilities document is broken"),
    ).toBeInTheDocument();
  });

  it("shows the indeterminate bar when the total is unknown", () => {
    state.store = storeOf([
      job({ id: 1, totalSteps: null, doneSteps: null, progress: null }),
      job({ id: 2, totalSteps: 6, doneSteps: 2, progress: 33 }),
    ]);
    render(<JobCenterDrawer />);
    const bars = panel().getAllByRole("progressbar");
    expect(bars).toHaveLength(2);
    expect(bars[0]).toHaveAttribute("data-indeterminate", "true");
    expect(bars[1]).toHaveAttribute("data-indeterminate", "false");
    expect(panel().getAllByText("chip:state")).toHaveLength(2);
  });

  it("opens the running and failed rows and collapses the decided success", () => {
    state.store = storeOf([
      job({ id: 1, description: "Register weather service" }),
      job({
        id: 2,
        status: "failed",
        state: "failed",
        description: "Harvest counties",
        errorSummary: "connection refused",
        doneAt: "2026-11-10T11:00:00Z",
      }),
      job({
        id: 3,
        status: "completed",
        state: "completed",
        description: "Index counties",
        doneAt: "2026-11-10T12:00:00Z",
      }),
    ]);
    render(<JobCenterDrawer />);
    const rows = panel();
    // running work and failures are open when they appear; only the
    // completed row sits collapsed behind its chevron
    expect(rows.getAllByRole("status")).toHaveLength(2);
    expect(
      rows.getByRole("button", {
        name: "backgroundActivity.jobCenter.expandJob",
      }),
    ).toHaveAttribute("aria-expanded", "false");
    // the failure offers the persistent details of the decided process
    expect(
      rows.getByRole("link", { name: "backgroundActivity.viewDetails" }),
    ).toHaveAttribute("href", "/BackgroundProcess/2/show");
  });

  it("folds the details of a row behind its chevron", () => {
    state.store = storeOf([
      job({
        id: 3,
        status: "completed",
        state: "completed",
        description: "Index counties",
        doneAt: "2026-11-10T12:00:00Z",
      }),
    ]);
    render(<JobCenterDrawer />);
    const rows = panel();
    // the first line stays while the details are folded away
    expect(rows.getByText("Index counties")).toBeInTheDocument();
    expect(rows.queryByRole("status")).toBeNull();
    const expand = rows.getByRole("button", {
      name: "backgroundActivity.jobCenter.expandJob",
    });
    fireEvent.click(expand);
    expect(
      rows.getByRole("button", {
        name: "backgroundActivity.jobCenter.collapseJob",
      }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(rows.getByRole("status")).toHaveTextContent("chip:state");
    fireEvent.click(
      rows.getByRole("button", {
        name: "backgroundActivity.jobCenter.collapseJob",
      }),
    );
    expect(rows.queryByRole("status")).toBeNull();
    expect(rows.getByText("Index counties")).toBeInTheDocument();
  });

  it("narrows the rows through the search and says so when none match", () => {
    state.store = storeOf([
      job({ id: 1, description: "Register weather service" }),
      job({ id: 2, description: "Harvest counties" }),
    ]);
    render(<JobCenterDrawer />);
    fireEvent.change(panel().getByLabelText("backgroundActivity.jobCenter.search"), {
      target: { value: "counties" },
    });
    expect(panel().queryByText("Register weather service")).toBeNull();
    expect(panel().getByText("Harvest counties")).toBeInTheDocument();
    fireEvent.change(panel().getByLabelText("backgroundActivity.jobCenter.search"), {
      target: { value: "nothing" },
    });
    expect(
      panel().getByText("backgroundActivity.jobCenter.searchEmpty"),
    ).toBeInTheDocument();
  });

  it("filters the failed tab onto the decided failures and tells the reason", () => {
    state.store = storeOf([
      job({ id: 1, description: "Register weather service" }),
      job({
        id: 2,
        status: "failed",
        state: "failed",
        description: "Harvest counties",
        errorSummary: "connection refused",
        doneAt: "2026-11-10T11:00:00Z",
      }),
    ]);
    render(<JobCenterDrawer />);
    fireEvent.click(screen.getByRole("tab", { name: /tabs.failed/ }));
    const rows = panel();
    expect(rows.queryByText("Register weather service")).toBeNull();
    expect(rows.getByText("Harvest counties")).toBeInTheDocument();
    expect(rows.getByText("connection refused")).toBeInTheDocument();
    expect(rows.getByText("date:doneAt")).toBeInTheDocument();
  });

  it("points at the full list when the tab cannot render every row", () => {
    state.store = storeOf(
      Array.from({ length: 51 }, (_, index) =>
        job({ id: index + 1, description: `job ${index}` }),
      ),
    );
    render(<JobCenterDrawer />);
    expect(
      panel().getByText("backgroundActivity.jobCenter.truncated"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "backgroundActivity.viewAll" }),
    ).toHaveAttribute("href", "/BackgroundProcess");
  });

  it("answers the history tab with the realtime list of the decided processes", () => {
    state.history.data = [
      job({
        id: 9,
        status: "completed",
        state: "completed",
        description: "Index counties",
        doneAt: "2026-11-10T12:00:00Z",
      }),
    ];
    render(<JobCenterDrawer />);
    fireEvent.click(screen.getByRole("tab", { name: /tabs.history/ }));
    expect(state.realtimeProps).toMatchObject({
      resource: "BackgroundProcess",
      filter: { status: "completed,aborted" },
    });
    expect(screen.getByText("Index counties")).toBeInTheDocument();
  });

  it("tells the loading state of the history while it is pending", () => {
    state.history.isPending = true;
    render(<JobCenterDrawer />);
    fireEvent.click(screen.getByRole("tab", { name: /tabs.history/ }));
    expect(
      screen.getByRole("progressbar", { name: "ra.message.loading" }),
    ).toBeInTheDocument();
  });

  it("clears the completed only while there are any", () => {
    const clear = () =>
      screen.getByRole("button", {
        name: "backgroundActivity.jobCenter.clearCompleted",
      });
    render(<JobCenterDrawer />);
    expect(clear()).toBeDisabled();
    state.store = storeOf([
      job({ id: 1, status: "completed", state: "completed" }),
    ]);
    render(<JobCenterDrawer />);
    fireEvent.click(clear());
    expect(state.clearCompleted).toHaveBeenCalled();
  });

  it("leaves through the history button and closes on the close button", () => {
    render(<JobCenterDrawer />);
    fireEvent.click(
      screen.getByRole("link", {
        name: "backgroundActivity.jobCenter.openHistory",
      }),
    );
    expect(state.setOpen).toHaveBeenLastCalledWith(false);
    fireEvent.click(screen.getByLabelText("ra.action.close"));
    expect(state.setOpen).toHaveBeenLastCalledWith(false);
  });
});
