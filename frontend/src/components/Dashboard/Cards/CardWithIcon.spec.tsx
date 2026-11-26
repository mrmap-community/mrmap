import { MemoryRouter } from "react-router-dom";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CardWithIcon from "./CardWithIcon";

const state = vi.hoisted(() => ({
  stats: { status: "ready", days: [], inventory: null } as unknown,
  count: { total: 12, isPending: false, filterValues: {} },
}));

vi.mock("react-admin", () => ({
  useResourceContext: () => "CatalogueService",
  useListContext: () => state.count,
  useLocaleState: () => ["en"],
  useTranslate: () => (key: string, options?: Record<string, string>) => {
    if (key === "resources.CatalogueService.plural") return "Catalogues";
    if (options?.delta) return `Change ${options.delta}`;
    if (options?.percent) return `${options.percent} from the period start`;
    return key;
  },
}));

vi.mock("../useDashboardStatistics", () => ({
  useDashboardStatistics: () => state.stats,
}));

vi.mock("@mui/x-charts/SparkLineChart", () => ({
  SparkLineChart: ({ data }: { data: number[] }) => <div data-testid="sparkline">{data.join(",")}</div>,
}));

const icon = () => null;

beforeEach(() => {
  state.count = { total: 12, isPending: false, filterValues: {} };
  state.stats = { status: "ready", days: [], inventory: null };
});

describe("compact CardWithIcon", () => {
  it("shows a localized title and authoritative current count", () => {
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" title="CatalogueService" compact /></MemoryRouter>);
    expect(screen.getByText("Catalogues")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("renders signed delta and percent without an unsupported dummy trend", () => {
    state.stats = {
      status: "ready",
      days: [{ id: "2026-11-25", new: 0, updated: 0, deleted: 1, total: 11 },
        { id: "2026-11-26", new: 0, updated: 0, deleted: 0, total: 12 }],
      inventory: { baseline: 10, delta: 2, percent: 20 },
    };
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" title="CatalogueService" compact /></MemoryRouter>);
    expect(screen.getByText("Change +2 · +20% from the period start")).toBeInTheDocument();
    expect(screen.getByTestId("sparkline")).toHaveTextContent("11,12");
  });

  it("does not invent a percentage for a zero baseline", () => {
    state.stats = {
      status: "ready",
      days: [{ id: "2026-11-26", new: 0, updated: 0, deleted: 0, total: 0 }],
      inventory: { baseline: 0, delta: 0, percent: null },
    };
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" title="CatalogueService" compact /></MemoryRouter>);
    expect(screen.getByText(/dashboard.kpi.noPercent/)).toBeInTheDocument();
  });

  it("does not draw a trend for unsupported statistics", () => {
    state.stats = { status: "unsupported" };
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" title="CatalogueService" compact /></MemoryRouter>);
    expect(screen.queryByTestId("sparkline")).not.toBeInTheDocument();
    expect(screen.getByText("historyChart.noStatistics")).toBeInTheDocument();
  });
});
