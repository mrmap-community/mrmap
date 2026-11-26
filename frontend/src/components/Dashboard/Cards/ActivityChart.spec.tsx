import type { ActivitySource } from "../dashboardActivity";

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import de from "../../../i18n/de";
import en from "../../../i18n/en";
import { dashboardStatistics } from "../dashboardStatistics";
import ActivityChart from "./ActivityChart";

type Line = {
  id: string; label: string; data: number[]; color: string; curve: string;
  area: boolean; showMark: boolean; shape: string; valueFormatter: (value: number | null) => string;
};
type PlotProps = {
  "aria-label"?: string;
  height: number;
  series: Line[];
  hiddenItems: { seriesId: string }[];
  onHiddenItemsChange: (items: unknown[]) => void;
  slotProps: { legend: { direction?: string; toggleVisibilityOnClick?: boolean } };
  xAxis: {
    data: string[]; height: number;
    valueFormatter: (day: string, context: { location: string }) => string;
    tickInterval: (day: string, index: number) => boolean;
  }[];
  yAxis: {
    min: number; max?: number; tickNumber?: number; tickMinStep?: number; domainLimit?: string; width: number | string; label: string;
    valueFormatter: (value: number) => string;
  }[];
  grid: { horizontal: boolean; vertical: boolean };
};

const state = vi.hoisted(() => ({ sources: [] as ActivitySource[], locale: "en", query: vi.fn(), chart: vi.fn() }));
const lookup = (key: string) => {
  let value: unknown = state.locale === "de" ? de : en;
  for (const part of key.split(".")) value = (value as Record<string, unknown>)?.[part];
  return typeof value === "string" ? value : key;
};
/** the answer of the card and of the popover for a resource which cannot answer */
const messageOf = { loading: "asking", error: "error", partial: "partial", unsupported: "noStatistics" } as const;
vi.mock("react-admin", () => ({
  useLocaleState: () => [state.locale],
  useTranslate: () => (key: string, options: Record<string, unknown> = {}) => {
    const message = lookup(key);
    return (message === key ? String(options._ ?? key) : message)
      .replace(/%\{(\w+)\}/g, (_all: string, name: string) => String(options[name]));
  },
}));
vi.mock("../useDashboardActivity", () => ({
  useDashboardActivity: (resources: string[], period: number) => {
    state.query(resources, period);
    return state.sources.filter(source => resources.includes(source.resource));
  },
}));
vi.mock("@mui/x-charts/LineChart", () => ({
  LineChart: (props: PlotProps) => {
    state.chart(props);
    return <>
      <div aria-label="Native series legend" />
      <div data-testid="activity-lines">{props.series
        .filter(line => !props.hiddenItems.some(hidden => hidden.seriesId === line.id))
        .map(line => <span key={line.id}>{line.id}: {line.data.join(",")}</span>)}</div>
    </>;
  },
}));

const source = (resource: string, added: number, updated = 0, deleted = 0): ActivitySource => ({
  resource, statistics: dashboardStatistics([
    { id: "2026-11-26", day: "2026-11-26", new: added, updated, deleted },
  ], 1, 100, 30, "2026-11-26"),
});
const resources = ["CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord", "WebMapService"];
const plot = (): PlotProps => state.chart.mock.lastCall?.[0] as PlotProps;
const lines = () => screen.getByTestId("activity-lines");
const zero = (value: number) => `0,${"0,".repeat(28)}${value}`;
const choosePeriod = (option: string) => {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: lookup("dashboard.activity.period") }));
  fireEvent.click(screen.getByRole("option", { name: option }));
};
const openCoverage = () => {
  fireEvent.click(screen.getByRole("button", { name: lookup("dashboard.activity.coverage") }));
  return screen.getByRole("dialog", { name: lookup("dashboard.activity.coverage") });
};

beforeEach(() => {
  state.locale = "en";
  state.sources = [
    source("CatalogueService", 10, 3, 2),
    source("DatasetMetadataRecord", 20, 4, 1),
    source("ServiceMetadataRecord", 30, 5, 0),
  ];
  state.chart.mockClear();
  state.query.mockClear();
});

describe("ActivityChart", () => {
  it("draws one line per authorized resource, in the color of that resource", () => {
    render(<ActivityChart resources={resources} />);
    expect(state.query).toHaveBeenLastCalledWith(resources, 30);
    expect(plot().series.map(line => line.id)).toEqual([
      "CatalogueService", "DatasetMetadataRecord", "ServiceMetadataRecord",
    ]);
    expect(plot().series.map(line => line.label)).toEqual([
      "Catalogue Service", "Dataset metadata records", "Service metadata records",
    ]);
    expect(plot().series.map(line => line.color)).toEqual(["#ed6c02", "#2e7d32", "#1976d2"]);
    expect(lines()).toHaveTextContent(`CatalogueService: ${zero(15)}`);
    expect(lines()).toHaveTextContent(`DatasetMetadataRecord: ${zero(25)}`);
    expect(lines()).toHaveTextContent(`ServiceMetadataRecord: ${zero(35)}`);
  });

  it("draws the plot with the native features of the mockup", () => {
    render(<ActivityChart resources={resources} />);
    const props = plot();
    expect(props["aria-label"]).toBe("Changes to services and metadata");
    expect(screen.getByRole("heading", { name: "Changes to services and metadata" })).toBeInTheDocument();
    expect(props.height).toBeLessThanOrEqual(180);
    expect(props.series.every(line =>
      line.curve === "linear" && line.area && line.showMark && line.shape === "circle")).toBe(true);
    expect(props.grid).toEqual({ horizontal: true, vertical: true });
    expect(props.yAxis[0]).toMatchObject({ min: 0, max: 40, tickNumber: 5, domainLimit: "strict", label: "Number of changes" });
    expect(props.slotProps.legend).toMatchObject({ direction: "horizontal", toggleVisibilityOnClick: true });
    expect(screen.getAllByLabelText("Native series legend")).toHaveLength(1);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("keeps the card compact: no permanent scope text, no totals block, no second filter", () => {
    render(<ActivityChart resources={resources} />);
    expect(screen.queryByText(/histories complete/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Additions|Updates|Deletions/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("combobox")).toHaveLength(1);
    expect(screen.getByRole("combobox", { name: "Period" })).toHaveTextContent("Last 30 days");
  });

  it("names sparse localized days and keeps the exact value in the tooltip", () => {
    state.sources = [source("ServiceMetadataRecord", 20000)];
    render(<ActivityChart resources={resources} />);
    const props = plot();
    expect(props.xAxis[0].data).toHaveLength(30);
    expect(props.xAxis[0].data.filter((_day, index) => props.xAxis[0].tickInterval("", index))).toHaveLength(10);
    expect(props.xAxis[0].valueFormatter("2026-11-26", { location: "tick" })).toBe("Nov 26");
    expect(props.xAxis[0].valueFormatter("2026-11-26", { location: "tooltip" })).toBe("Nov 26, 2026");
    expect(props.yAxis[0]).toMatchObject({ min: 0, max: 20000, tickNumber: 5, domainLimit: "strict" });
    expect(props.series[0].valueFormatter(20000)).toBe("20,000");
    expect(props.yAxis[0].valueFormatter(20000)).toBe("20,000");
  });

  it("preserves the true spike of one day instead of smoothing it", () => {
    state.sources = [source("ServiceMetadataRecord", 20000)];
    render(<ActivityChart resources={resources} />);
    const data = plot().series[0].data;
    expect(data.filter(value => value === 20000)).toHaveLength(1);
    expect(data.at(-1)).toBe(20000);
    expect(data.filter(value => value > 0)).toHaveLength(1);
  });

  it("toggles the one legend without asking the api again and recovers from no series", () => {
    render(<ActivityChart resources={resources} />);
    const asked = state.query.mock.calls.length;
    const hidden = plot().series.map(line => ({ type: "line" as const, seriesId: line.id }));
    act(() => plot().onHiddenItemsChange(hidden));
    expect(screen.getByRole("status")).toHaveTextContent("Unhide a resource in the legend");
    expect(screen.getByTestId("activity-lines")).toBeEmptyDOMElement();
    act(() => plot().onHiddenItemsChange(hidden.slice(0, 1)));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(lines()).toHaveTextContent("DatasetMetadataRecord:");
    expect(lines()).not.toHaveTextContent("CatalogueService:");
    expect(state.query.mock.calls).toHaveLength(asked);
  });

  it("changes the verified period", () => {
    render(<ActivityChart resources={resources} />);
    choosePeriod("Last 7 days");
    expect(state.query).toHaveBeenLastCalledWith(resources, 7);
    choosePeriod("Last 90 days");
    expect(state.query).toHaveBeenLastCalledWith(resources, 90);
  });

  it.each(["partial", "error", "loading", "unsupported"] as const)(
    "draws the verified resources and names a %s one instead of inventing a line", status => {
      state.sources[1].statistics = { status };
      render(<ActivityChart resources={resources} />);
      expect(lines()).toHaveTextContent("CatalogueService:");
      expect(lines()).not.toHaveTextContent("DatasetMetadataRecord:");
      expect(screen.getByRole("status")).toHaveTextContent("Dataset metadata records cannot answer right now");
      const dialog = openCoverage();
      expect(within(dialog).getByText(new RegExp(`^Dataset metadata records: ${lookup(`historyChart.${messageOf[status]}`)}`)))
        .toBeInTheDocument();
      expect(within(dialog).getByText(/^Catalogue Service: Complete for the selected period/)).toBeInTheDocument();
      expect(within(dialog).getByText(/No verified dashboard history:/)).toHaveTextContent("Web Map Services");
    });

  it.each(["partial", "error", "loading", "unsupported"] as const)(
    "answers the %s state of the whole card when no resource can be drawn", status => {
      for (const entry of state.sources) entry.statistics = { status };
      render(<ActivityChart resources={resources} />);
      expect(screen.queryByTestId("activity-lines")).not.toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent(lookup(`historyChart.${messageOf[status]}`));
    });

  it("distinguishes a verified zero from a resource which cannot answer", () => {
    state.sources = [{ resource: "CatalogueService", statistics: dashboardStatistics([], 0, 0, 30, "2026-11-26") }];
    const { rerender } = render(<ActivityChart resources={resources} />);
    expect(lines()).toHaveTextContent(`CatalogueService: ${zero(0)}`);
    expect(screen.getByText("No changes recorded in this period.")).toBeInTheDocument();
    rerender(<ActivityChart resources={[]} />);
    expect(screen.queryByTestId("activity-lines")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("No change statistics");
  });

  it("drops a resource as soon as its permission disappears", () => {
    const { rerender } = render(<ActivityChart resources={resources} />);
    rerender(<ActivityChart resources={["DatasetMetadataRecord"]} />);
    expect(plot().series.map(line => line.id)).toEqual(["DatasetMetadataRecord"]);
  });

  it("explains the statistical scope on demand, with totals and the exact window", () => {
    render(<ActivityChart resources={resources} />);
    const dialog = openCoverage();
    expect(dialog).toHaveTextContent("audit events, never distinct objects");
    expect(within(dialog).getByText(/^Service metadata records: Complete for the selected period/)).toBeInTheDocument();
    expect(dialog).toHaveTextContent("35 Events");
    expect(dialog).toHaveTextContent("Oct 28, 2026 – Nov 26, 2026 (30 calendar days, Europe/Berlin)");
  });

  it("localizes the card, the axes and the popover in German", () => {
    state.locale = "de";
    render(<ActivityChart resources={resources} />);
    expect(screen.getByRole("heading", { name: "Änderungen an Diensten und Metadaten" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Zeitraum" })).toHaveTextContent("Letzte 30 Tage");
    const props = plot();
    expect(props.yAxis[0].label).toBe("Anzahl Änderungen");
    expect(props.series[0].valueFormatter(1000)).toBe("1.000");
    expect(props.yAxis[0].valueFormatter(1000)).toBe("1.000");
    expect(props.xAxis[0].valueFormatter("2026-11-26", { location: "tick" })).toBe("26. Nov.");
    expect(props.xAxis[0].valueFormatter("2026-11-26", { location: "tooltip" })).toBe("26. Nov. 2026");
    expect(within(openCoverage()).getByText(/^Dienstemetadatensätze: Vollständig für den gewählten Zeitraum/)).toBeInTheDocument();
  });
});
