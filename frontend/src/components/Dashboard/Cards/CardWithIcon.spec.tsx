import { MemoryRouter } from "react-router-dom";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CardWithIcon from "./CardWithIcon";

const state = vi.hoisted(() => ({
  locale: "en",
  stats: { status: "ready", days: [], inventory: null } as unknown,
  count: { total: 12 as number | undefined, isPending: false, error: undefined as unknown, filterValues: {} },
}));

vi.mock("react-admin", () => ({
  useResourceContext: () => "CatalogueService",
  useListContext: () => state.count,
  useLocaleState: () => [state.locale],
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

vi.mock("../../Resource/Generic/History/HistoryChart", () => ({
  HistoryChartCore: () => <div>History chart</div>,
}));

const icon = () => null;

beforeEach(() => {
  state.locale = "en";
  state.count = { total: 12, isPending: false, error: undefined, filterValues: {} };
  state.stats = { status: "ready", days: [], inventory: null };
});

describe("compact CardWithIcon", () => {
  it("shows a localized title and authoritative current count", () => {
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" title="CatalogueService" compact /></MemoryRouter>);
    expect(screen.getByText("Catalogues")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("formats the current count using the selected German locale", () => {
    state.locale = "de";
    state.count.total = 1234;
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" compact /></MemoryRouter>);
    expect(screen.getByText("1.234")).toBeInTheDocument();
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

  it.each(["loading", "error", "partial", "unsupported"])("shows the %s statistics fallback", (status) => {
    const messages: Record<string, string> = {
      loading: "historyChart.asking", error: "historyChart.error",
      partial: "historyChart.partial", unsupported: "historyChart.noStatistics",
    };
    state.stats = { status };
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" compact /></MemoryRouter>);
    expect(screen.getByText(messages[status])).toBeInTheDocument();
    expect(screen.queryByTestId("sparkline")).not.toBeInTheDocument();
  });

  it.each(["pending", "error", "missing"])("handles a %s current count", (status) => {
    state.count.isPending = status === "pending";
    state.count.error = status === "error" ? new Error("unavailable") : undefined;
    state.count.total = status === "missing" ? undefined : 12;
    const { container } = render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" compact /></MemoryRouter>);
    expect(screen.queryByText("12")).not.toBeInTheDocument();
    if (status === "pending") expect(container.querySelector(".MuiSkeleton-root")).toBeInTheDocument();
    else expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("formats negative changes and ignores a non-finite percentage and unknown totals", () => {
    state.stats = {
      status: "ready",
      days: [{ total: null }, { total: 10 }, { total: 8 }],
      inventory: { delta: -2, percent: Number.NaN },
    };
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" compact /></MemoryRouter>);
    expect(screen.getByText("Change −2")).toBeInTheDocument();
    expect(screen.getByTestId("sparkline")).toHaveTextContent("10,8");
  });

  it("formats a negative percentage", () => {
    state.stats = { status: "ready", days: [], inventory: { delta: -2, percent: -20 } };
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" compact /></MemoryRouter>);
    expect(screen.getByText("Change −2 · −20% from the period start")).toBeInTheDocument();
  });
});

describe("standard CardWithIcon", () => {
  it("preserves its title, subtitle, history and children", () => {
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" title="Catalogues" subtitle="12"><span>Content</span></CardWithIcon></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Catalogues 12" })).toHaveAttribute("href", "/CatalogueService");
    expect(screen.getByText("History chart")).toBeInTheDocument();
    expect(screen.getByText("Content")).toBeInTheDocument();
  });

  it("shows a statistics error instead of a chart", () => {
    state.stats = { status: "error" };
    render(<MemoryRouter><CardWithIcon icon={icon} to="/CatalogueService" title="Catalogues" /></MemoryRouter>);
    expect(screen.getByText("historyChart.error")).toBeInTheDocument();
    expect(screen.queryByText("History chart")).not.toBeInTheDocument();
  });
});
