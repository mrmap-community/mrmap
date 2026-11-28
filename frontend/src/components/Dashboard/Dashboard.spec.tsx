import { fireEvent, render, screen } from "@testing-library/react";
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

/** the reads of the screen, answered by the two shared hooks of #1820 */
const reads = vi.hoisted(() => ({
  inventory: [] as { resource: string; status: string }[],
  counts: [] as { resource: string; status: string }[],
  inventoryCalls: [] as { resources: string[]; period: number }[],
  countCalls: [] as string[][],
  refreshes: 0,
  period: 30,
}));

vi.mock("react-admin", () => ({
  useCanAccessResources: () => ({ canAccess: access.canAccess, isPending: access.isPending }),
  useLocaleState: () => ["en"],
  useTranslate: () => (key: string) => key,
}));

vi.mock("./useDashboardPeriod", async () => {
  const { useState } = await import("react");
  return {
    DASHBOARD_PERIODS: [7, 30, 90],
    useDashboardPeriod: () => {
      const [period, setPeriod] = useState<number>(reads.period);
      return {
        period,
        setPeriod,
        refresh: () => { reads.refreshes += 1; },
        refreshedAt: null as number | null,
      };
    },
  };
});

vi.mock("./useDashboardInventory", () => ({
  inventoryKpiResources: [
    "WebMapService", "Layer", "WebFeatureService", "FeatureType",
    "CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord",
  ],
  useDashboardInventory: (resources: string[], period: number) => {
    reads.inventoryCalls.push({ resources, period });
    return reads.inventory.filter(source => resources.includes(source.resource));
  },
  useDashboardCounts: (resources: string[]) => {
    reads.countCalls.push(resources);
    return reads.counts.filter(source => resources.includes(source.resource));
  },
}));

vi.mock("./Cards/BackgroundProcessesCard", () => ({
  default: () => <div>backgroundProcesses</div>,
}));

vi.mock("./Cards/ActivityChart", () => ({
  default: ({ resources, period }: { resources: string[]; period: number }) => (
    <div data-testid="activity-chart">{resources.join(",")}@{period}</div>
  ),
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

vi.mock("./Cards/InventoryChart", () => ({
  default: ({ sources }: { sources: { resource: string }[] }) => (
    <div data-testid="inventory-chart">{sources.map(source => source.resource).join(",")}</div>
  ),
}));

vi.mock("./Cards/DailyChangesChart", () => ({
  default: ({ sources, period }: { sources: { resource: string }[]; period: number }) => (
    <div data-testid="daily-changes">
      {sources.map(source => source.resource).join(",")}@{period}
    </div>
  ),
}));

vi.mock("./Cards/InventoryDistributionCard", () => ({
  default: ({ sources }: { sources: { resource: string }[] }) => (
    <div data-testid="distribution">{sources.map(source => source.resource).join(",")}</div>
  ),
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

/** the seven inventory kinds of the mockup, in the order it answers them */
const kinds = [
  "WebMapService", "Layer", "WebFeatureService", "FeatureType",
  "CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord",
];

const answerEverything = () => {
  reads.inventory = kinds.map(resource => ({ resource, status: "ready" }));
  reads.counts = kinds.map(resource => ({ resource, status: "ready" }));
};

beforeEach(() => {
  access.isPending = false;
  for (const key of Object.keys(access.canAccess)) access.canAccess[key] = true;
  reads.inventory = [];
  reads.counts = [];
  reads.inventoryCalls = [];
  reads.counts = [];
  reads.countCalls = [];
  reads.refreshes = 0;
  reads.period = 30;
});

const askedResources = () =>
  screen.getAllByText(/^inventory /).map(element => element.textContent ?? "");

describe("Dashboard", () => {
  it("answers the critical states above everything and the work which waits beside the inventory", () => {
    answerEverything();
    const { container } = render(<Dashboard />);
    const asked = screen
      .getAllByText(/critical|workQueue|attention|inventory/)
      .map(element => element.textContent);
    // what is broken is read before the counts of the registry
    expect(asked[0]).toBe("critical");
    expect(asked.indexOf("critical")).toBeLessThan(
      asked.indexOf("inventory WebMapService false true"),
    );
    // the header of the screen precedes the critical answers, because it is the
    // one which decides over which window they all answer (#1820)
    expect(screen.getByRole("heading", { name: "dashboard.header.title" })).toBeInTheDocument();

    // the queue and the alerts of the services are one column of the row the
    // changes and the distribution answer in, so the exceptions are read beside
    // the answers of the inventory instead of pushing them down the page (#1816)
    const queue = screen.getByText("workQueue");
    expect(queue.parentElement).toBe(screen.getByText("attention").parentElement);
    const column = queue.parentElement?.parentElement;
    const grid = container.querySelectorAll(".MuiGrid-container")[2];
    expect(column?.parentElement).toBe(grid);
    expect(grid).toContainElement(screen.getByTestId("daily-changes"));
    expect(grid).toContainElement(screen.getByTestId("distribution"));
  });

  it("answers which work waits and which services carry a problem", () => {
    answerEverything();
    render(<Dashboard />);
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("workQueue")).toBeInTheDocument();
    expect(screen.getByText("attention")).toBeInTheDocument();
  });

  it("answers the whole permitted inventory in its known order", () => {
    answerEverything();
    render(<Dashboard />);
    expect(askedResources()).toEqual(kinds.map(resource => `inventory ${resource} false true`));
  });

  it("never mounts an unauthorized list", () => {
    answerEverything();
    access.canAccess.CatalogueService = false;
    access.canAccess.Organization = false;
    access.canAccess.User = false;
    render(<Dashboard />);
    expect(askedResources()).not.toContain("inventory CatalogueService false true");
    expect(screen.queryByText(/Organization/)).not.toBeInTheDocument();
    expect(screen.queryByText(/User/)).not.toBeInTheDocument();
  });

  it("renders loading inventory skeletons while permissions are unresolved", () => {
    access.isPending = true;
    const { container } = render(<Dashboard />);
    expect(container.querySelectorAll(".MuiSkeleton-root")).toHaveLength(kinds.length);
    expect(screen.queryByTestId("activity-chart")).not.toBeInTheDocument();
    expect(reads.inventoryCalls).toEqual([{ resources: [], period: 30 }]);
  });

  it("gives the permitted resources and the shared period to every answer of the screen", () => {
    answerEverything();
    access.canAccess.CatalogueService = false;
    access.canAccess.User = false;
    render(<Dashboard />);
    const permitted = kinds.filter(resource => resource !== "CatalogueService");
    const chart = screen.getByTestId("activity-chart");
    expect(chart).not.toHaveTextContent("CatalogueService");
    expect(chart).not.toHaveTextContent("User");
    expect(chart).toHaveTextContent("DatasetMetadataRecord");
    // the two complementary charts of #1820 read the same resources and the same
    // window the activity chart draws, so no card of the screen disagrees about
    // the days it names
    expect(screen.getByTestId("inventory-chart")).toHaveTextContent(permitted.join(","));
    expect(screen.getByTestId("daily-changes")).toHaveTextContent(`${permitted.join(",")}@30`);
    expect(chart).toHaveTextContent("@30");
    expect(reads.inventoryCalls).toEqual([{ resources: permitted, period: 30 }]);
    expect(reads.countCalls).toEqual([permitted]);
  });

  it("answers the distribution from the counts of the same permitted kinds", () => {
    answerEverything();
    reads.counts = [
      { resource: "Layer", status: "ready" },
      { resource: "FeatureType", status: "ready" },
    ];
    render(<Dashboard />);
    expect(screen.getByTestId("distribution")).toHaveTextContent("Layer,FeatureType");
  });

  it("verifies the window the header chose over the whole screen", () => {
    answerEverything();
    render(<Dashboard />);
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "dashboard.header.period" }));
    // the first option of the selector is the shortest window
    fireEvent.click(screen.getAllByRole("option")[0]);
    expect(reads.inventoryCalls.at(-1)).toEqual({ resources: kinds, period: 7 });
    expect(screen.getByTestId("activity-chart")).toHaveTextContent("@7");
    expect(screen.getByTestId("daily-changes")).toHaveTextContent("@7");
  });

  it("refreshes the whole screen at once", () => {
    answerEverything();
    render(<Dashboard />);
    fireEvent.click(screen.getByRole("button", { name: "dashboard.header.refresh" }));
    expect(reads.refreshes).toBe(1);
  });

  it("answers the running background processes beside the notices of the deployment", () => {
    answerEverything();
    const { container } = render(<Dashboard />);
    const processes = screen.getByText("backgroundProcesses");
    const chart = screen.getByTestId("activity-chart");
    // the tables of the deployment are a row of their own, below the rows of the
    // charts ...
    const row = processes.parentElement as HTMLElement;
    expect(row).not.toBe(chart.parentElement);
    expect(container.querySelector(".MuiBox-root:last-of-type")?.contains(row)).toBe(true);
    // ... with the notices of the deployment in the left half and the processes
    // in the right one
    const notices = screen.getByTestId("notices").parentElement as HTMLElement;
    expect(row.parentElement).toBe(notices.parentElement);
    expect(row.previousElementSibling).toBe(notices);
    expect(notices).toHaveClass("MuiGrid-grid-md-6");
    expect(row).toHaveClass("MuiGrid-grid-md-6");
    // the table asks nothing of its own: the card reads the store of the job
    // center, so no list controller of BackgroundProcess is mounted here
    expect(screen.queryByText(/inventory BackgroundProcess/)).not.toBeInTheDocument();
  });

  it("does not mount the cards of the deployment while permissions are unresolved", () => {
    access.isPending = true;
    render(<Dashboard />);
    expect(screen.queryByText("backgroundProcesses")).not.toBeInTheDocument();
    expect(screen.queryByTestId("distribution")).not.toBeInTheDocument();
  });

  it("leaves no layout wrapper dividers or spacers of its own", () => {
    answerEverything();
    const { container } = render(<Dashboard />);
    expect(container.querySelector("hr")).toBeNull();
  });
});
