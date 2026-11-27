import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Dashboard from "./Dashboard";

const access = vi.hoisted(() => ({
  isPending: false,
  canAccess: Object.fromEntries([
    "WebMapService", "Layer", "WebFeatureService", "FeatureType",
    "CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord",
    "Organization", "User",
  ].map(resource => [resource, true])) as Record<string, boolean>,
}));

vi.mock("react-admin", () => ({
  useCanAccessResources: () => ({ canAccess: access.canAccess, isPending: access.isPending }),
}));

vi.mock("./Cards/BackgroundProcessesCard", () => ({
  default: () => <div>backgroundProcesses</div>,
}));

vi.mock("./Cards/ActivityChart", () => ({
  default: ({ resources }: { resources: string[] }) => <div data-testid="activity-chart">{resources.join(",")}</div>,
}));

vi.mock("./Cards/CriticalAlerts", () => ({
  default: () => <div>critical</div>,
}));

vi.mock("./Cards/WorkQueueCard", () => ({
  default: () => <div>workQueue</div>,
}));

vi.mock("./Cards/RecentNoticesCard", () => ({
  default: ({ resources }: { resources: string[] }) => <div data-testid="notices">{resources.join(",")}</div>,
}));

vi.mock("./Cards/ServiceAttentionCard", () => ({
  default: () => <div>attention</div>,
}));

vi.mock("./Cards/ResourceListCard", () => ({
  default: ({
    resource,
    withList = true,
    compact = false,
  }: {
    resource: string;
    withList?: boolean;
    compact?: boolean;
  }) => <div>{`inventory ${resource} ${withList} ${compact}`}</div>,
}));

beforeEach(() => {
  access.isPending = false;
  for (const key of Object.keys(access.canAccess)) access.canAccess[key] = true;
});

/** the inventory the dashboard asks, in the order it answers it */
const inventory = [
  "inventory WebMapService false true",
  "inventory Layer false true",
  "inventory WebFeatureService false true",
  "inventory FeatureType false true",
  "inventory CatalogueService false true",
  "inventory DatasetMetadataRecord false true",
  "inventory ServiceMetadataRecord false true",
  "inventory Organization false true",
  "inventory User false true",
];

const askedResources = () =>
  screen
    .getAllByText(/^inventory /)
    .map((element) => element.textContent ?? "");

describe("Dashboard", () => {
  it("answers the critical states above everything and the work which waits beside the inventory", () => {
    const { container } = render(<Dashboard />);
    const asked = screen
      .getAllByText(/critical|workQueue|attention|inventory/)
      .map((element) => element.textContent);
    // what is broken is read before the counts of the registry
    expect(asked[0]).toBe("critical");
    expect(asked.indexOf("critical")).toBeLessThan(
      asked.indexOf("inventory WebMapService false true"),
    );

    // the health of the deployment and the alerts of its services answer one
    // column of the same grid the inventory answers, so the exceptions are read
    // in the middle-right of the screen instead of pushing the counts down the
    // page (#1816)
    const health = screen.getByText("workQueue");
    expect(health.parentElement).toBe(
      screen.getByText("attention").parentElement,
    );
    // the stack of the two cards is one grid item of the grid the inventory
    // answers in
    const column = health.parentElement?.parentElement;
    const grid = container.querySelector(".MuiGrid-container");
    expect(column?.parentElement).toBe(grid);
    expect(grid).toContainElement(
      screen.getByText("inventory WebMapService false true"),
    );
  });

  it("answers which work waits and which services carry a problem", () => {
    render(<Dashboard />);
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("workQueue")).toBeInTheDocument();
    expect(screen.getByText("attention")).toBeInTheDocument();
  });

  it("answers the whole permitted inventory in its known order", () => {
    render(<Dashboard />);
    expect(askedResources()).toEqual(inventory);
  });

  it("never mounts an unauthorized organization or user list", () => {
    access.canAccess.Organization = false;
    access.canAccess.User = false;
    render(<Dashboard />);
    expect(screen.queryByText(/Organization/)).not.toBeInTheDocument();
    expect(screen.queryByText(/User/)).not.toBeInTheDocument();
  });

  it("renders loading inventory skeletons while permissions are unresolved", () => {
    access.isPending = true;
    const { container } = render(<Dashboard />);
    expect(container.querySelectorAll(".MuiSkeleton-root")).toHaveLength(9);
    expect(screen.queryByTestId("activity-chart")).not.toBeInTheDocument();
  });

  it("only gives permitted resources to the activity chart", () => {
    access.canAccess.CatalogueService = false;
    access.canAccess.User = false;
    render(<Dashboard />);
    expect(screen.getByTestId("activity-chart")).not.toHaveTextContent("CatalogueService");
    expect(screen.getByTestId("activity-chart")).not.toHaveTextContent("User");
    expect(screen.getByTestId("activity-chart")).toHaveTextContent("DatasetMetadataRecord");
  });

  it("answers the running background processes in the bottom-right of the screen", () => {
    const { container } = render(<Dashboard />);
    const processes = screen.getByText("backgroundProcesses");
    const chart = screen.getByTestId("activity-chart");
    // the table of the work is a row of its own, below the row of the chart ...
    const row = processes.parentElement as HTMLElement;
    expect(row).not.toBe(chart.parentElement);
    // the row of the table follows the row of the chart in the document
    expect(
      container.querySelector(".MuiBox-root:last-of-type")?.contains(row),
    ).toBe(true);
    // The notices occupy the left half; processes follow in the right half.
    const notices = screen.getByTestId("notices").parentElement as HTMLElement;
    expect(row.parentElement).toBe(notices.parentElement);
    expect(row.previousElementSibling).toBe(notices);
    expect(notices).toHaveClass("MuiGrid-grid-md-6");
    expect(row).toHaveClass("MuiGrid-grid-md-6");
    // the table asks nothing of its own: the card reads the store of the job
    // center, so no list controller of BackgroundProcess is mounted here
    expect(
      screen.queryByText(/inventory BackgroundProcess/),
    ).not.toBeInTheDocument();
  });

  it("does not mount the processes table while permissions are unresolved", () => {
    access.isPending = true;
    render(<Dashboard />);
    expect(screen.queryByText("backgroundProcesses")).not.toBeInTheDocument();
  });

  it("leaves no layout wrapper dividers or spacers of its own", () => {
    const { container } = render(<Dashboard />);
    expect(container.querySelector("span")).toBeNull();
  });
});
