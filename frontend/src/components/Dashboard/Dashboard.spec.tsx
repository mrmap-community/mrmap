import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Dashboard from "./Dashboard";

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
  }: {
    resource: string;
    withList?: boolean;
  }) => <div>{`inventory ${resource} ${withList}`}</div>,
}));

/** the inventory the dashboard asks, in the order it answers it */
const inventory = [
  "inventory WebMapService false",
  "inventory Layer false",
  "inventory WebFeatureService false",
  "inventory FeatureType false",
  "inventory CatalogueService false",
  "inventory DatasetMetadataRecord false",
  "inventory ServiceMetadataRecord false",
  "inventory Organization true",
  "inventory User true",
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
      asked.indexOf("inventory WebMapService false"),
    );
    expect(asked.indexOf("attention")).toBeLessThan(
      asked.indexOf("inventory WebMapService false"),
    );
  });

  it("answers which work waits and which services carry a problem", () => {
    render(<Dashboard />);
    expect(screen.getByText("workQueue")).toBeInTheDocument();
    expect(screen.getByText("attention")).toBeInTheDocument();
  });

  it("answers the whole inventory in its known groups and order", () => {
    render(<Dashboard />);
    expect(askedResources()).toEqual(inventory);
  });

  it("asks the compact cards without a list and accounts with one", () => {
    render(<Dashboard />);
    const asked = askedResources();
    expect(asked.every((entry) => entry.endsWith(" false"))).toBe(false);
    expect(asked.filter((entry) => entry.endsWith(" true"))).toEqual([
      "inventory Organization true",
      "inventory User true",
    ]);
  });

  it("leaves no layout wrapper dividers or spacers of its own", () => {
    const { container } = render(<Dashboard />);
    expect(container.querySelector("span")).toBeNull();
  });
});
