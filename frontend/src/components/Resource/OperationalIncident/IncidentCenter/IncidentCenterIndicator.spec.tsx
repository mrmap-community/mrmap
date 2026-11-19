import type { OperationalIncidentRecord } from "../incidentContract";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import IncidentCenterIndicator from "./IncidentCenterIndicator";

const state = vi.hoisted(() => ({
  open: false,
  setOpen: vi.fn(),
  wide: true,
  active: {
    data: [] as OperationalIncidentRecord[],
    total: 3,
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

vi.mock("@mui/material", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@mui/material")>()),
  useMediaQuery: () => state.wide,
}));

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
}));

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
  lastOccurredAt: "2026-11-14T10:00:00Z",
  ...overrides,
});

beforeEach(() => {
  state.open = false;
  state.setOpen = vi.fn();
  state.wide = true;
  state.active = {
    data: [],
    total: 3,
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

describe("IncidentCenterIndicator", () => {
  it("shows the permitted active total and opens the center on a click", () => {
    render(<IncidentCenterIndicator />);
    const button = screen.getByRole("button", {
      name: "incidentCenter.activeCount",
    });
    expect(button).toHaveTextContent("3");
    fireEvent.click(button);
    expect(state.setOpen).toHaveBeenCalledWith(true);
  });

  it("says nothing while the read is pending, while it failed and while nothing is active", () => {
    state.active.isPending = true;
    const { rerender } = render(<IncidentCenterIndicator />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();

    state.active.isPending = false;
    state.active.error = new Error("Service Unavailable");
    rerender(<IncidentCenterIndicator />);
    // a failing read is silence, not a hint that incidents could be there -
    // an error must never become an alert the permitted data does not back
    expect(screen.queryByRole("button")).not.toBeInTheDocument();

    state.active.error = null;
    state.active.total = 0;
    rerender(<IncidentCenterIndicator />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps the whole message in the accessible name", () => {
    // a screen reader hears "3 active incidents" through the translated
    // count - the bare number carries its sentence in the name (#1321)
    render(<IncidentCenterIndicator />);
    expect(
      screen.getByRole("button", { name: "incidentCenter.activeCount" }),
    ).toBeInTheDocument();
  });

  it("gives way to a badge over the icon on narrow screens", () => {
    state.wide = false;
    state.active.data = [
      incident({ id: "1", severity: "error" }),
      incident({ id: "2", severity: "warning" }),
    ];
    state.active.total = 2;
    render(<IncidentCenterIndicator />);
    fireEvent.click(
      screen.getByRole("button", {
        name: "incidentCenter.activeCount",
      }),
    );
    expect(state.setOpen).toHaveBeenCalledWith(true);
    // the count survives the narrow layout as the badge content
    expect(screen.getByText("2")).toBeInTheDocument();
  });
});
