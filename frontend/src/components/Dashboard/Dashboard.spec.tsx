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

vi.mock("./Cards/ActivityChart", () => ({
  default: ({ resources }: { resources: string[] }) => <div data-testid="activity-chart">{resources.join(",")}</div>,
}));

vi.mock("./Cards/WorkQueueCard", () => ({
  default: () => <div>workQueue</div>,
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
  it("answers the work which waits before the inventory", () => {
    render(<Dashboard />);
    const answered = screen.getAllByText(/workQueue|attention|inventory/);
    const asked = answered.map((element) => element.textContent);
    expect(asked.slice(0, 2)).toEqual(["workQueue", "attention"]);
    expect(asked.indexOf("workQueue")).toBeLessThan(
      asked.indexOf("inventory WebMapService false true"),
    );
    expect(asked.indexOf("attention")).toBeLessThan(
      asked.indexOf("inventory WebMapService false true"),
    );
  });

  it("answers which work waits and which services carry a problem", () => {
    render(<Dashboard />);
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

  it("leaves no layout wrapper dividers or spacers of its own", () => {
    const { container } = render(<Dashboard />);
    expect(container.querySelector("span")).toBeNull();
  });
});
