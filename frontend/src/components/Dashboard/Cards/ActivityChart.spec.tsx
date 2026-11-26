import type { ActivitySource } from "../dashboardActivity";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import de from "../../../i18n/de";
import en from "../../../i18n/en";
import { dashboardStatistics } from "../dashboardStatistics";
import ActivityChart from "./ActivityChart";

const state = vi.hoisted(() => ({ sources: [] as ActivitySource[], locale: "en", query: vi.fn(), chart: vi.fn() }));
const lookup = (key: string) => {
  let value: unknown = state.locale === "de" ? de : en;
  for (const part of key.split(".")) value = (value as Record<string, unknown>)?.[part];
  return typeof value === "string" ? value : key;
};
vi.mock("react-admin", () => ({
  useLocaleState: () => [state.locale],
  useTranslate: () => (key: string, options: Record<string, unknown> = {}) =>
    lookup(key).replace(/%\{(\w+)\}/g, (_, name: string) => String(options[name])),
}));
vi.mock("../useDashboardActivity", () => ({
  useDashboardActivity: (resources: string[], period: number) => {
    state.query(resources, period);
    return state.sources.filter(source => resources.includes(source.resource));
  },
}));
vi.mock("@mui/x-charts/LineChart", () => ({
  LineChart: (props: { series: { id: string; data: number[] }[] }) => {
    state.chart(props);
    return <div data-testid="activity-lines">{props.series.map(series => <span key={series.id}>{series.id}: {series.data.join(",")}</span>)}</div>;
  },
}));

const source = (resource: string, added: number): ActivitySource => ({
  resource, statistics: dashboardStatistics([
    { id: "2026-11-26", day: "2026-11-26", new: added, updated: 2, deleted: 1 },
  ], 1, 100, 30, "2026-11-26"),
});
const resources = ["CatalogueService", "DatasetMetadataRecord", "WebMapService"];
const choose = (label: string, option: string) => {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: label }));
  fireEvent.click(screen.getByRole("option", { name: option }));
};

beforeEach(() => {
  state.locale = "en";
  state.sources = [source("CatalogueService", 10), source("DatasetMetadataRecord", 20)];
  state.chart.mockClear();
  state.query.mockClear();
});

describe("ActivityChart", () => {
  it("defaults to 30 days, aggregates events and makes coverage and exclusions explicit", () => {
    render(<ActivityChart resources={resources} />);
    expect(state.query).toHaveBeenLastCalledWith(resources, 30);
    expect(screen.getByLabelText("Event totals for the selected period")).toHaveTextContent("30");
    expect(screen.getByText(/No verified dashboard history:/)).toHaveTextContent("Web Map Services");
    expect(screen.getAllByText(/Complete for the selected period/)).toHaveLength(2);
    expect(screen.getByText("Dataset metadata records: Complete for the selected period")).toBeInTheDocument();
    const props = state.chart.mock.lastCall?.[0];
    expect(props.series.map((series: { id: string }) => series.id)).toEqual(["new", "updated", "deleted"]);
    expect(props.series.every((series: { curve: string; data: number[] }) => series.curve === "linear" && series.data.every(value => value >= 0))).toBe(true);
    expect(props.yAxis[0]).toMatchObject({ min: 0, tickMinStep: 1 });
    expect(props.xAxis[0].valueFormatter("2026-11-26")).toContain("26");
    expect(props.series[0].valueFormatter(1000)).toBe("1,000");
  });

  it("filters one resource and changes verified periods", () => {
    render(<ActivityChart resources={resources} />);
    choose("Resource", lookup("resources.CatalogueService.plural"));
    expect(screen.getByLabelText("Event totals for the selected period")).toHaveTextContent("10");
    expect(state.chart.mock.lastCall?.[0].series[0].data.at(-1)).toBe(10);
    choose("Period", "Last 7 days");
    expect(state.query).toHaveBeenLastCalledWith(resources, 7);
    choose("Period", "Last 90 days");
    expect(state.query).toHaveBeenLastCalledWith(resources, 90);
  });

  it("toggles each event series without altering totals or query parameters", () => {
    render(<ActivityChart resources={resources} />);
    for (const name of ["Additions", "Updates", "Deletions"]) fireEvent.click(screen.getByRole("checkbox", { name }));
    expect(screen.queryByTestId("activity-lines")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Select an event series");
    fireEvent.click(screen.getByRole("checkbox", { name: "Updates" }));
    expect(state.chart.mock.lastCall?.[0].series.map((series: { id: string }) => series.id)).toEqual(["updated"]);
    expect(state.query).toHaveBeenLastCalledWith(resources, 30);
  });

  it.each(["partial", "error", "loading", "unsupported"] as const)("does not aggregate %s history", status => {
    state.sources[1].statistics = { status };
    render(<ActivityChart resources={resources} />);
    expect(screen.queryByTestId("activity-lines")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Event totals for the selected period")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
    // A complete resource remains available when another resource has no usable history.
    choose("Resource", lookup("resources.CatalogueService.plural"));
    expect(screen.getByTestId("activity-lines")).toBeInTheDocument();
  });

  it("distinguishes a verified zero from unavailable history", () => {
    state.sources = [{ resource: "CatalogueService", statistics: dashboardStatistics([], 0, 0, 30, "2026-11-26") }];
    const { rerender } = render(<ActivityChart resources={resources} />);
    expect(screen.getByText("No changes recorded in this period.")).toBeInTheDocument();
    expect(screen.getByTestId("activity-lines")).toBeInTheDocument();
    rerender(<ActivityChart resources={[]} />);
    expect(screen.queryByTestId("activity-lines")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("No change statistics");
  });

  it("drops a selected resource immediately when its permission disappears", () => {
    const { rerender } = render(<ActivityChart resources={resources} />);
    choose("Resource", lookup("resources.CatalogueService.plural"));
    rerender(<ActivityChart resources={["DatasetMetadataRecord"]} />);
    expect(state.chart.mock.lastCall?.[0].series[0].data.at(-1)).toBe(20);
    expect(screen.getByRole("combobox", { name: "Resource" })).toHaveTextContent("All supported resources");
  });

  it("localizes controls, totals, series, dates and tooltips in German", () => {
    state.locale = "de";
    render(<ActivityChart resources={resources} />);
    expect(screen.getByRole("combobox", { name: "Zeitraum" })).toHaveTextContent("Letzte 30 Tage");
    expect(screen.getByRole("checkbox", { name: "Neuaufnahmen" })).toBeInTheDocument();
    expect(screen.getByText("Datenmetadatensätze: Vollständig für den gewählten Zeitraum")).toBeInTheDocument();
    const totals = screen.getByLabelText("Ereignissummen im gewählten Zeitraum");
    expect(within(totals).getByText("30")).toBeInTheDocument();
    const props = state.chart.mock.lastCall?.[0];
    expect(props.series[0].valueFormatter(1000)).toBe("1.000");
    expect(props.xAxis[0].valueFormatter("2026-11-26")).toBe("26. Nov. 2026");
  });
});
