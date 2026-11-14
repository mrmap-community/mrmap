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
    // sourceType of the api stays readable, as JobCenterDrawer practices it
    useTranslate: () => (key: string, options?: Record<string, unknown>) =>
      options !== undefined && options._ !== undefined
        ? String(options._)
        : key,
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
  id: 1,
  code: "harvest.chord_stalled",
  sourceType: "harvesting",
  severity: "warning",
  state: "retrying",
  summary: "CSW endpoint did not respond",
  occurrenceCount: 1,
  firstOccurrence: "2026-11-14T10:00:00Z",
  lastOccurrence: "2026-11-14T11:00:00Z",
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
        id: 1,
        occurrenceCount: 10,
        retryAttempt: 4,
        retryTotal: 10,
        nextRetryAt: "2026-11-14T14:37:00Z",
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
    // the epic's sentence: retry 4/10, next attempt ... (#1104)
    expect(
      rows.getByText(
        "incidentCenter.retryAttempt · incidentCenter.retryOfTotal · incidentCenter.nextAttempt",
      ),
    ).toBeInTheDocument();
    // first and last occurrence are both there, as relative moments
    expect(rows.getByText("date:firstOccurrence")).toBeInTheDocument();
    expect(rows.getByText("date:lastOccurrence")).toBeInTheDocument();
  });

  it("links only to the destination the server permitted", () => {
    state.active.data = [
      incident({ id: 1, targetPath: "/HarvestingJob/7/show" }),
      incident({ id: 2, summary: "Private catalogue trouble", targetPath: null }),
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
    // the row whose target the client may not see offers no destination and
    // derives none - no path, no resource name, no guess
    expect(
      panel().getByText("Private catalogue trouble"),
    ).toBeInTheDocument();
    expect(panel().getAllByRole("link")).toHaveLength(1);
  });

  it("narrows the window through the facet chips and says so when none match", () => {
    state.active.data = [
      incident({ id: 1, severity: "error", summary: "Update failed hard" }),
      incident({ id: 2, severity: "warning", sourceType: "monitoring" }),
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

  it("distinguishes retrying, suspected stalled and failed by state", () => {
    state.active.data = [
      incident({ id: 1, state: "retrying" }),
      incident({ id: 2, state: "stalled" }),
      incident({ id: 3, state: "failed", severity: "error" }),
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
    state.active.data = [incident({ id: 1 })];
    state.active.total = 1;
    state.resolved.data = [
      incident({
        id: 2,
        summary: "CSW endpoint answered again",
        state: "resolved",
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
    state.active.error = new Error("list_OperationalIncident not found");
    state.resolved.error = new Error("list_OperationalIncident not found");
    render(<IncidentCenterDrawer />);
    expect(
      panel().getByText("incidentCenter.loadError"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "ra.action.refresh" }));
    expect(state.active.refetch).toHaveBeenCalledTimes(1);
    // while the api of #1319 is not there at all, the resolved window fails
    // too and the other tab says its own silence - not a crash
    fireEvent.click(screen.getByRole("tab", { name: /tabs.resolved/ }));
    expect(
      panel().getByText("incidentCenter.loadError"),
    ).toBeInTheDocument();
  });

  it("names rows beyond the bounded window instead of hiding them", () => {
    state.active.data = [incident({ id: 1 }), incident({ id: 2 })];
    state.active.total = 25 + 7;
    render(<IncidentCenterDrawer />);
    expect(
      panel().getByText("incidentCenter.truncated"),
    ).toBeInTheDocument();
  });
});
