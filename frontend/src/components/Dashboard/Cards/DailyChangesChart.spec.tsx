import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import de from "../../../i18n/de";
import en from "../../../i18n/en";
import {
  dashboardDailyChanges,
  type InventorySource,
} from "../dashboardInventory";
import { dashboardStatistics } from "../dashboardStatistics";
import DailyChangesChart from "./DailyChangesChart";

type BarProps = {
  series: { id: string; label: string; data: number[]; stack: string; color: string }[];
  hiddenItems: { type: string; seriesId: string }[];
  onHiddenItemsChange: (items: { type: string; seriesId: string }[]) => void;
  xAxis: {
    data: string[];
    valueFormatter: (value: string, context: { location: string }) => string;
  }[];
  yAxis: {
    min?: number; max?: number; label?: string;
    valueFormatter?: (value: number) => string;
  }[];
  "aria-label"?: string;
};

const state = vi.hoisted(() => ({
  sources: [] as InventorySource[],
  locale: "en",
  chart: vi.fn(),
}));

const lookup = (key: string) => {
  let value: unknown = state.locale === "de" ? de : en;
  for (const part of key.split(".")) value = (value as Record<string, unknown>)?.[part];
  return typeof value === "string" ? value : key;
};

vi.mock("react-admin", () => ({
  useLocaleState: () => [state.locale],
  useTranslate: () => (key: string, options: Record<string, unknown> = {}) => {
    const message = lookup(key);
    return (message === key ? String(options._ ?? key) : message)
      .replace(/%\{(\w+)\}/g, (_all: string, name: string) => String(options[name]));
  },
}));

vi.mock("@mui/x-charts/BarChart", () => ({
  BarChart: (props: BarProps) => {
    state.chart(props);
    return <>
      <div aria-label="Native series legend" />
      <div data-testid="stacked-bars">{props.series
        .filter(bar => !props.hiddenItems.some(hidden => hidden.seriesId === bar.id))
        .map(bar => <span key={bar.id}>{bar.id}: {bar.data.join(",")}</span>)}</div>
    </>;
  },
}));

/** the source of a resource whose events of the last day of the window are given */
const source = (
  resource: string,
  events: { added?: number; updated?: number; deleted?: number },
  today: string = "2026-11-26",
): InventorySource => {
  const statistics = dashboardStatistics([
    {
      id: today, day: today,
      new: events.added ?? 0, updated: events.updated ?? 0, deleted: events.deleted ?? 0,
    },
  ], 1, 100, 30, today);
  if (statistics.status !== "ready") throw Error("the fixture is not verified");
  return {
    resource,
    status: "ready",
    days: statistics.days,
    count: (events.added ?? 0) + (events.updated ?? 0) + (events.deleted ?? 0),
  };
};

const plot = (): BarProps => state.chart.mock.lastCall?.[0] as BarProps;
const bars = () => screen.getByTestId("stacked-bars");
const zero = (value: number) => `0,${"0,".repeat(28)}${value}`;

beforeEach(() => {
  state.locale = "en";
  state.sources = [
    source("CatalogueService", { added: 1, updated: 2, deleted: 3 }),
    source("DatasetMetadataRecord", { added: 10, updated: 4, deleted: 1 }),
    source("ServiceMetadataRecord", { added: 2, updated: 0, deleted: 0 }),
  ];
  state.chart.mockClear();
});

describe("DailyChangesChart", () => {
  it("stacks one bar per verified resource of the window, in the color of that resource", () => {
    render(<DailyChangesChart sources={state.sources} period={30} />);
    expect(bars()).toHaveTextContent(`CatalogueService: ${zero(6)}`);
    expect(bars()).toHaveTextContent(`DatasetMetadataRecord: ${zero(15)}`);
    expect(plot().series.every(bar => bar.stack === "events")).toBe(true);
    expect(new Set(plot().series.map(bar => bar.color)).size).toBe(3);
    expect(screen.getByRole("heading", { name: lookup("dashboard.changes.title") })).toBeInTheDocument();
  });

  it("answers the very totals the activity chart draws for the same window", () => {
    render(<DailyChangesChart sources={state.sources} period={30} />);
    const stacked = plot().series.map(bar => bar.data);
    const activity = dashboardDailyChanges(state.sources, 30);
    if (activity.status !== "ready") throw Error("the fixture is not verified");
    expect(stacked).toEqual(activity.series.map(line => line.data));
    // the subheader says the window it counted over, so the bar of a day is
    // never read as a stock
    expect(screen.getByText(lookup("dashboard.changes.scope").replace("%{days}", "30")))
      .toBeInTheDocument();
    expect(screen.getByText(/23 events over 30 days/)).toBeInTheDocument();
  });

  it("names the whole verified period in the tooltip of a day and a short label on the axis", () => {
    render(<DailyChangesChart sources={state.sources} period={30} />);
    const axis = plot().xAxis[0];
    const last = axis.data.at(-1) as string;
    expect(axis.valueFormatter(last, { location: "tooltip" })).not.toBe(last);
    expect(axis.valueFormatter(last, { location: "tick" })).not.toBe(last);
  });

  it("keeps the events of a resource which cannot answer out of the stack and names it", () => {
    state.sources[1] = { resource: "DatasetMetadataRecord", status: "error" };
    render(<DailyChangesChart sources={state.sources} period={30} />);
    expect(bars()).toHaveTextContent("CatalogueService:");
    expect(bars()).not.toHaveTextContent("DatasetMetadataRecord:");
    expect(screen.getByRole("status")).toHaveTextContent("Dataset metadata records");
    expect(screen.getByRole("status")).toHaveTextContent("cannot answer right now");
  });

  it.each(["partial", "error", "loading", "unsupported"] as const)(
    "answers the %s state of the whole card when nothing can be stacked", status => {
      state.sources = [{ resource: "CatalogueService", status }];
      render(<DailyChangesChart sources={state.sources} period={30} />);
      expect(state.chart).not.toHaveBeenCalled();
      expect(screen.getByRole("status")).toBeInTheDocument();
    });

  it("hides a stacked resource on its legend entry and says so when all are hidden", () => {
    render(<DailyChangesChart sources={state.sources} period={30} />);
    act(() => plot().onHiddenItemsChange([{ type: "bar", seriesId: "CatalogueService" }]));
    expect(bars()).not.toHaveTextContent("CatalogueService:");
    act(() => plot().onHiddenItemsChange(
      state.sources.map(entry => ({ type: "bar", seriesId: entry.resource })),
    ));
    expect(screen.getByRole("status")).toHaveTextContent(lookup("dashboard.activity.noSeries"));
  });

  it("answers a deployment without a single event as empty and not as broken", () => {
    state.sources = [source("CatalogueService", { added: 0 })];
    render(<DailyChangesChart sources={state.sources} period={30} />);
    expect(screen.getByRole("status")).toHaveTextContent(lookup("dashboard.activity.empty"));
  });

  it("counts the values of the axis as whole numbers in the locale of the user", () => {
    state.locale = "de";
    state.sources = [source("CatalogueService", { added: 1234 })];
    render(<DailyChangesChart sources={state.sources} period={30} />);
    expect(screen.getByRole("heading", { name: "Tägliche Änderungen nach Ressource" })).toBeInTheDocument();
    const axis = plot().yAxis[0];
    expect(axis.label).toBe("Anzahl Ereignisse");
    expect(axis.valueFormatter?.(1234)).toBe("1.234");
  });

  it("answers the same window as the header of the screen", () => {
    render(<DailyChangesChart sources={state.sources} period={30} />);
    expect(plot().xAxis[0].data).toHaveLength(30);
    expect(plot().xAxis[0].data.at(-1)).toBe("2026-11-26");
  });
});
