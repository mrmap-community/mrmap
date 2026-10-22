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
  default: ({ resource }: { resource: string }) => (
    <div>inventory {resource}</div>
  ),
}));

describe("Dashboard", () => {
  it("answers the work which waits before the inventory", () => {
    render(<Dashboard />);
    const answered = screen.getAllByText(/workQueue|attention|inventory/);
    const asked = answered.map((element) => element.textContent);
    expect(asked.slice(0, 2)).toEqual(["workQueue", "attention"]);
    expect(asked.indexOf("workQueue")).toBeLessThan(
      asked.indexOf("inventory WebMapService"),
    );
    expect(asked.indexOf("attention")).toBeLessThan(
      asked.indexOf("inventory WebMapService"),
    );
  });

  it("answers which work waits and which services carry a problem", () => {
    render(<Dashboard />);
    expect(screen.getByText("workQueue")).toBeInTheDocument();
    expect(screen.getByText("attention")).toBeInTheDocument();
  });
});
