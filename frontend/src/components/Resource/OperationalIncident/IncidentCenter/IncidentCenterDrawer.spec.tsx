import type { OperationalIncidentRecord } from "../incidentContract";

import type { AnchorHTMLAttributes } from "react";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IncidentCenterDrawer from "./IncidentCenterDrawer";

const state = vi.hoisted(() => ({
  open: true,
  setOpen: vi.fn(),
  active: {
    data: [] as OperationalIncidentRecord[],
    total: 0,
    isPending: false,
    error: null as Error | null,
    refetch: vi.fn(),
  },
  resolved: {
    data: [] as OperationalIncidentRecord[],
    total: 0,
    isPending: false,
    error: null as Error | null,
    refetch: vi.fn(),
  },
}));

vi.mock("./IncidentCenterContext", () => ({
  useIncidentCenter: () => ({
    active: state.active,
    resolved: state.resolved,
    open: state.open,
    setOpen: state.setOpen,
  }),
}));

vi.mock("../../../Field/RelativeDateField", () => ({
  default: ({ source }: { source: string }) => <span>{`date:${source}`}</span>,
}));

vi.mock("react-admin", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  const RecordContext = React.createContext<
    Record<string, unknown> | undefined
  >(undefined);
  return {
    RecordContext,
    useRecordContext: () => React.useContext(RecordContext),
    // the `_` option answers a value which is no translation key - a raw
    // source of the api stays readable, as JobCenterDrawer practices it
    useTranslate: () => (key: string, options?: Record<string, unknown>) =>
      options !== undefined && options._ !== undefined
        ? String(options._)
        : key,
    // the same show-view path react-admin builds, so the href pins what the
    // link of the row really is
    useCreatePath: () => (params: { resource: string; id: string }) =>
      `/${params.resource}/${params.id}/show`,
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

const incident = (
  overrides: Partial<OperationalIncidentRecord>,
): OperationalIncidentRecord => ({
  id: "1",
  code: "harvesting_harvest_all_records",
  source: "harvesting",
  severity: "warning",
  status: "active",
  scope: "resource",
  summary: "CSW endpoint did not respond",
  occurrenceCount: 1,
  firstOccurredAt: "2026-11-14T10:00:00Z",
  lastOccurredAt: "2026-11-14T11:00:00Z",
  ...overrides,
});

/** the visible tab panel: the hidden one of the other tab is excluded from
 *  `getByRole` by MUI's own `hidden` attribute (JobCenterDrawer's answer) */
const panel = () => within(screen.getByRole("tabpanel"));

beforeEach(() => {
  state.open = true;
  state.setOpen = vi.fn();
  state.active = {
    data: [],
    total: 0,
    isPending: false,
    error: null,
    refetch: vi.fn(),
  };
  state.resolved = {
    data: [],
    total: 0,
    isPending: false,
    error: null,
    refetch: vi.fn(),
  };
  vi.clearAllMocks();
});

describe("IncidentCenterDrawer", () => {
  it("renders nothing while closed and the titled dialog while open", () => {
    state.open = false;
    const { rerender } = render(<IncidentCenterDrawer />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    state.open = true;
    rerender(<IncidentCenterDrawer />);
    expect(
      screen.getByRole("dialog", { name: "incidentCenter.title" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("ra.action.close"));
    expect(state.setOpen).toHaveBeenCalledWith(false);
  });

  it("answers an empty active window without drama and names what emptiness means", () => {
    render(<IncidentCenterDrawer />);
    expect(panel().getByText("incidentCenter.emptyActive")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /tabs.resolved/ }));
    expect(
      panel().getByText("incidentCenter.emptyResolved"),
    ).toBeInTheDocument();
  });

  it("shows one recurring incident as one row with the folded occurrence count", () => {
    // the server folded ten retries into one record; the drawer must not
    // invent rows per retry - the record is keyed by its stable id (#1321)
    state.active.data = [
      incident({
        id: "1",
        occurrenceCount: 10,
        retryCount: 4,
        retryScheduledUntil: "2026-11-14T14:37:00Z",
      }),
    ];
    state.active.total = 1;
    render(<IncidentCenterDrawer />);
    const rows = panel();
    expect(rows.getByText("CSW endpoint did not respond")).toBeInTheDocument();
    expect(rows.getAllByRole("listitem")).toHaveLength(1);
    // the count chip carries the folded occurrences and says the moment away
    expect(
      rows.getByLabelText("incidentCenter.occurrences"),
    ).toBeInTheDocument();
    // the retries the reported operation told, and until when the next
    // attempt is due - only what the api answers (#1104)
    expect(
      rows.getByText(
        "incidentCenter.retryCount · incidentCenter.nextAttempt",
      ),
    ).toBeInTheDocument();
    // first and last occurrence are both there, as relative moments
    expect(rows.getByText("date:firstOccurredAt")).toBeInTheDocument();
    expect(rows.getByText("date:lastOccurredAt")).toBeInTheDocument();
  });

  it("links the resource the api named and gives a system incident no destination", () => {
    // permission is the list's own (#1319): whatever row is here may be
    // opened, so the row links to exactly the type-and-id the answer names -
    // and a system incident, which names no resource, gets no link
    state.active.data = [
      incident({
        id: "1",
        affectedResource: { type: "HarvestingJob", id: "7" },
      }),
      incident({
        id: "2",
        summary: "Queue without a consumer",
        scope: "system",
        affectedResource: null,
      }),
    ];
    state.active.total = 2;
    render(<IncidentCenterDrawer />);
    const link = panel().getByRole("link", {
      name: "incidentCenter.openTarget",
    });
    expect(link).toHaveAttribute("href", "/HarvestingJob/7/show");
    fireEvent.click(link);
    // navigating to the permitted resource leaves the drawer
    expect(state.setOpen).toHaveBeenCalledWith(false);
    // the system incident shows its summary and derives no destination from
    // the code, the source or the id - nothing to click
    expect(
      panel().getByText("Queue without a consumer"),
    ).toBeInTheDocument();
    expect(panel().getAllByRole("link")).toHaveLength(1);
  });

  it("narrows the window through the facet chips and says so when none match", () => {
    state.active.data = [
      incident({ id: "1", severity: "error", summary: "Update failed hard" }),
      incident({ id: "2", severity: "warning", source: "monitoring" }),
    ];
    state.active.total = 2;
    render(<IncidentCenterDrawer />);
    fireEvent.click(
      screen.getByRole("button", {
        name: "incidentCenter.severities.error",
      }),
    );
    const rows = panel();
    expect(rows.getByText("Update failed hard")).toBeInTheDocument();
    expect(rows.queryByText("CSW endpoint did not respond")).toBeNull();
    // the toggle is announced as a toggle for keyboard and screen readers
    expect(
      screen.getByRole("button", {
        name: "incidentCenter.severities.error",
      }),
    ).toHaveAttribute("aria-pressed", "true");
    // the source facet chip reads back the raw value the api named
    expect(
      screen.getByRole("button", { name: "monitoring" }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "monitoring" }),
    );
    // error AND monitoring - the two active rows' intersection is empty
    expect(
      panel().getByText("incidentCenter.emptyFiltered"),
    ).toBeInTheDocument();
  });

  it("distinguishes retrying, suspected stalled and failed from the answered fields", () => {
    // no lifecycle field of four exists on the api - the reading comes from
    // the watchdog code family, the severity and the status (#1104)
    state.active.data = [
      incident({ id: "1", summary: "harvest waits for its next page" }),
      incident({
        id: "2",
        summary: "Retry window of the run expired",
        code: "operational_retry_window_expired",
        severity: "warning",
      }),
      incident({
        id: "3",
        summary: "Update exhausted its retry budget",
        severity: "error",
      }),
    ];
    state.active.total = 3;
    render(<IncidentCenterDrawer />);
    const rows = panel();
    for (const word of ["retrying", "stalled", "failed"]) {
      expect(
        rows.getByText(`incidentCenter.states.${word}`),
      ).toBeInTheDocument();
    }
    // the state facet offers the active states of the window
    expect(
      screen.getByRole("button", {
        name: "incidentCenter.states.stalled",
      }),
    ).toBeInTheDocument();
  });

  it("keeps recovery out of the active tab and visible in the resolved one", () => {
    state.active.data = [incident({ id: "1" })];
    state.active.total = 1;
    state.resolved.data = [
      incident({
        id: "2",
        summary: "CSW endpoint answered again",
        status: "resolved",
        severity: "warning",
        resolvedAt: "2026-11-14T12:00:00Z",
      }),
    ];
    state.resolved.total = 1;
    render(<IncidentCenterDrawer />);
    // the tab labels carry the totals of their own permitted windows
    expect(
      screen.getByRole("tab", { name: /tabs.active 1/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: /tabs.resolved 1/ }),
    ).toBeInTheDocument();
    expect(
      panel().queryByText("CSW endpoint answered again"),
    ).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: /tabs.resolved/ }));
    const rows = panel();
    expect(rows.getByText("CSW endpoint answered again")).toBeInTheDocument();
    expect(rows.getByText("date:resolvedAt")).toBeInTheDocument();
    // the state facet is the active window's question - every resolved row
    // answers "resolved", so the resolved tab does not offer it
    expect(
      screen.queryByRole("button", {
        name: "incidentCenter.states.stalled",
      }),
    ).toBeNull();
  });

  it("tells the loading state of a window", () => {
    state.active.isPending = true;
    render(<IncidentCenterDrawer />);
    expect(
      screen.getByRole("progressbar", { name: "ra.message.loading" }),
    ).toBeInTheDocument();
  });

  it("tells a failing read and offers the retry of it", () => {
    state.active.error = new Error("Service Unavailable");
    state.resolved.error = new Error("Service Unavailable");
    render(<IncidentCenterDrawer />);
    expect(
      panel().getByText("incidentCenter.loadError"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "ra.action.refresh" }));
    expect(state.active.refetch).toHaveBeenCalledTimes(1);
    // a failing endpoint fails both windows and the other tab says its own
    // silence - not a crash
    fireEvent.click(screen.getByRole("tab", { name: /tabs.resolved/ }));
    expect(
      panel().getByText("incidentCenter.loadError"),
    ).toBeInTheDocument();
  });

  it("names rows beyond the bounded window instead of hiding them", () => {
    state.active.data = [incident({ id: "1" }), incident({ id: "2" })];
    state.active.total = 25 + 7;
    render(<IncidentCenterDrawer />);
    expect(
      panel().getByText("incidentCenter.truncated"),
    ).toBeInTheDocument();
  });
});
