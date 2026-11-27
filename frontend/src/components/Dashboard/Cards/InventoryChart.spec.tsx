import type { InventorySource } from "../dashboardInventory";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import de from "../../../i18n/de";
import en from "../../../i18n/en";
import { dashboardStatistics } from "../dashboardStatistics";
import InventoryChart from "./InventoryChart";

type Line = {
  id: string; label: string; data: number[]; color: string; curve: string;
  area: boolean; showMark: boolean; valueFormatter: (value: number | null) => string;
};
type PlotProps = {
  "aria-label"?: string;
  height: number;
  series: Line[];
  hiddenItems: { seriesId: string }[];
  onHiddenItemsChange: (items: unknown[]) => void;
  slotProps: { legend: { direction?: string; toggleVisibilityOnClick?: boolean } };
  grid: { horizontal: boolean };
  xAxis: {
    data: string[];
    tickInterval: (day: string, index: number) => boolean;
    valueFormatter: (day: string, context: { location: string }) => string;
  }[];
  yAxis: {
    min?: number; max?: number; label?: string;
    valueFormatter?: (value: number) => string;
  }[];
};

const state = vi.hoisted(() => ({ sources: [] as InventorySource[], locale: "en", chart: vi.fn() }));
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

vi.mock("@mui/x-charts/LineChart", () => ({
  LineChart: (props: PlotProps) => {
    state.chart(props);
    return <>
      <div aria-label="Native series legend" />
      <div data-testid="inventory-lines">{props.series
        .filter(line => !props.hiddenItems.some(hidden => hidden.seriesId === line.id))
        .map(line => <span key={line.id}>{line.id}: {line.data.join(",")}</span>)}</div>
    </>;
  },
}));

/**
 * The source of a resource whose stock is provable: the window holds no audit
 * event at all, which is the only case in which the statistics of #1817 answer
 * a stock for every single day of it.
 */
const stock = (
  resource: string,
  count: number,
  period: 30 = 30,
  today: string = "2026-11-26",
): InventorySource => {
  const statistics = dashboardStatistics([], 0, count, period, today);
  if (statistics.status !== "ready") throw Error("the fixture is not verified");
  return { resource, status: "ready", days: statistics.days, count };
};

const plot = (): PlotProps => state.chart.mock.lastCall?.[0] as PlotProps;
const lines = () => screen.getByTestId("inventory-lines");
const flat = (value: number) => `${(String(value) + ",").repeat(29)}${value}`;
const openCoverage = () => {
  fireEvent.click(screen.getByRole("button", { name: lookup("dashboard.inventory.coverage") }));
  return screen.getByRole("dialog", { name: lookup("dashboard.inventory.coverage") });
};

beforeEach(() => {
  state.locale = "en";
  state.sources = [
    stock("CatalogueService", 12),
    stock("DatasetMetadataRecord", 40),
    stock("ServiceMetadataRecord", 0),
  ];
  state.chart.mockClear();
});

describe("InventoryChart", () => {
  it("draws one verified stock line per resource, in the color of that resource", () => {
    render(<InventoryChart sources={state.sources} />);
    expect(plot().series.map(line => line.id)).toEqual([
      "CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord",
    ]);
    expect(plot().series.map(line => line.label)).toEqual([
      "Catalogue Service", "Dataset metadata records", "Service metadata records",
    ]);
    // the same colors the activity chart (#1818) draws these resources with
    expect(plot().series.map(line => line.color)).toEqual(["#ed6c02", "#2e7d32", "#1976d2"]);
    expect(lines()).toHaveTextContent(`CatalogueService: ${flat(12)}`);
    expect(lines()).toHaveTextContent(`DatasetMetadataRecord: ${flat(40)}`);
  });

  it("draws the stock of a resource as a flat line and never as a cumulative one", () => {
    state.sources = [stock("CatalogueService", 12)];
    render(<InventoryChart sources={state.sources} />);
    const data = plot().series[0].data;
    expect(new Set(data)).toEqual(new Set([12]));
    // a cumulative reading of the same fixture would grow day by day
    expect(data[0]).toBe(data.at(-1));
  });

  it("names the value axis as a stock and never as events", () => {
    render(<InventoryChart sources={state.sources} />);
    const axis = plot().yAxis[0];
    expect(axis.label).toBe(lookup("dashboard.inventory.yAxis"));
    expect(axis.label).not.toBe(lookup("dashboard.activity.yAxis"));
    expect(axis).toMatchObject({ min: 0, domainLimit: "strict" });
    expect(axis.max).toBeGreaterThanOrEqual(40);
  });

  it("draws the plot with the native features of the mockup", () => {
    render(<InventoryChart sources={state.sources} />);
    const props = plot();
    expect(props["aria-label"]).toBe(lookup("dashboard.inventory.title"));
    expect(screen.getByRole("heading", { name: lookup("dashboard.inventory.title") })).toBeInTheDocument();
    expect(props.height).toBeLessThanOrEqual(180);
    expect(props.series.every(line => line.curve === "linear" && line.area && !line.showMark)).toBe(true);
    // a stock is read against its days, so the plot needs no vertical grid
    expect(props.grid).toEqual({ horizontal: true, vertical: false });
    expect(props.slotProps.legend).toMatchObject({ direction: "horizontal", toggleVisibilityOnClick: true });
    expect(screen.getAllByLabelText("Native series legend")).toHaveLength(1);
  });

  it("names sparse localized days and keeps the exact day in the tooltip", () => {
    render(<InventoryChart sources={state.sources} />);
    const props = plot();
    expect(props.xAxis[0].data).toHaveLength(30);
    expect(props.xAxis[0].data.filter((_day, index) => props.xAxis[0].tickInterval("", index)))
      .toHaveLength(10);
    expect(props.xAxis[0].valueFormatter("2026-11-26", { location: "tick" })).toBe("Nov 26");
    expect(props.xAxis[0].valueFormatter("2026-11-26", { location: "tooltip" })).toBe("Nov 26, 2026");
    expect(props.yAxis[0].valueFormatter?.(1234)).toBe("1,234");
  });

  it.each(["partial", "error", "loading", "unsupported"] as const)(
    "names a %s resource instead of inventing a stock line for it", status => {
      state.sources[1] = { resource: "DatasetMetadataRecord", status };
      render(<InventoryChart sources={state.sources} />);
      expect(lines()).toHaveTextContent("CatalogueService:");
      expect(lines()).not.toHaveTextContent("DatasetMetadataRecord:");
      expect(screen.getByRole("status")).toHaveTextContent("Dataset metadata records");
      const dialog = openCoverage();
      expect(within(dialog).getByText(new RegExp(
        `^Dataset metadata records: ${lookup("dashboard.inventory.unverified")}`,
      ))).toBeInTheDocument();
      expect(within(dialog).getByText(/^Catalogue Service: Verified stock, counts 12 today$/))
        .toBeInTheDocument();
    });

  it("names a resource whose stock the statistics leave ambiguous instead of drawing a zero", () => {
    const ambiguous = dashboardStatistics(
      [{ id: "2026-11-26", day: "2026-11-26", new: 3, updated: 0, deleted: 0 }],
      1, 3, 30, "2026-11-26",
    );
    if (ambiguous.status !== "ready") throw Error("the fixture is not verified");
    expect(ambiguous.days.some(day => day.total === null)).toBe(true);
    state.sources[1] = {
      resource: "DatasetMetadataRecord", status: "ready", days: ambiguous.days, count: 3,
    };
    render(<InventoryChart sources={state.sources} />);
    expect(lines()).not.toHaveTextContent("DatasetMetadataRecord:");
    expect(screen.getByRole("status")).toHaveTextContent("Dataset metadata records");
  });

  it.each(["partial", "error", "loading", "unsupported"] as const)(
    "answers the %s state of the whole card when no stock can be drawn", status => {
      state.sources = [{ resource: "CatalogueService", status }];
      render(<InventoryChart sources={state.sources} />);
      expect(state.chart).not.toHaveBeenCalled();
      expect(screen.getByRole("status")).toBeInTheDocument();
    });

  it("answers a verified deployment without any resource as empty and not as broken", () => {
    state.sources = [stock("CatalogueService", 0)];
    render(<InventoryChart sources={state.sources} />);
    expect(lines()).toHaveTextContent(`CatalogueService: ${flat(0)}`);
    expect(screen.getByRole("status")).toHaveTextContent(lookup("dashboard.inventory.empty"));
  });

  it("toggles the one legend without asking anything again and recovers from no line", () => {
    render(<InventoryChart sources={state.sources} />);
    const asked = state.chart.mock.calls.length;
    const hidden = plot().series.map(line => ({ type: "line" as const, seriesId: line.id }));
    act(() => plot().onHiddenItemsChange(hidden));
    expect(screen.getByRole("status")).toHaveTextContent(lookup("dashboard.activity.noSeries"));
    expect(lines()).toBeEmptyDOMElement();
    act(() => plot().onHiddenItemsChange(hidden.slice(0, 1)));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(lines()).toHaveTextContent("DatasetMetadataRecord:");
    expect(lines()).not.toHaveTextContent("CatalogueService:");
    expect(state.chart.mock.calls).toHaveLength(asked + 2);
  });

  it("says what its circle counts and over which window, in its coverage dialog", () => {
    render(<InventoryChart sources={state.sources} />);
    const dialog = openCoverage();
    expect(dialog).toHaveTextContent(lookup("dashboard.inventory.scope"));
    // the window the shared period of the header chose, named by its two ends
    expect(within(dialog).getByText(/calendar days/)).toBeInTheDocument();
    expect(dialog).toHaveTextContent("2026");
  });

  it("localizes the card, its axis and its dialog in German", () => {
    state.locale = "de";
    render(<InventoryChart sources={state.sources} />);
    expect(screen.getByRole("heading", { name: "Ressourcenbestand über die Zeit" })).toBeInTheDocument();
    expect(plot().yAxis[0].label).toBe("Anzahl registrierter Ressourcen");
    expect(plot().yAxis[0].valueFormatter?.(1234)).toBe("1.234");
    expect(openCoverage()).toHaveTextContent("Verifizierter Bestand, zählt heute 12");
  });

  it("answers a screen without any inventory at all without a chart", () => {
    render(<InventoryChart sources={[]} />);
    expect(state.chart).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
