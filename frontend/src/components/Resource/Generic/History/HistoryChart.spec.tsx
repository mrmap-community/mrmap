import type { ReactNode } from "react";
import type { RaRecord } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HistoryChart, {
  CHANGE_DAYS,
  changesOfDays,
  lastDays,
  namedDays,
} from "./HistoryChart";

const state = vi.hoisted(() => ({
  data: undefined as RaRecord[] | undefined,
  isPending: false,
  error: null as Error | null,
  /** whether the resource answers a statistical endpoint at all */
  hasStatistics: true,
  /** what the chart was asked to draw */
  series: [] as { data: number[]; label: string; stack?: string }[],
  days: [] as string[],
  /** how the chart names the days of the window it was asked to draw */
  axisLabel: undefined as ((day: string) => string) | undefined,
  axisTooltip: undefined as ((day: string) => string) | undefined,
}));

vi.mock("./HistoryListBase", () => ({
  default: ({
    children,
    fallback,
  }: {
    children?: ReactNode;
    fallback?: ReactNode;
  }) => (state.hasStatistics ? <>{children}</> : fallback),
}));

vi.mock("../../../MUI/GradientChartsContainer", () => ({
  default: ({
    series,
    xAxis,
  }: {
    series: { data: number[]; label: string; stack?: string }[];
    xAxis: {
      data: string[];
      labelFormatter?: (day: string) => string;
      valueFormatter?: (day: string) => string;
    }[];
  }) => {
    state.series = series;
    state.days = xAxis[0]?.data ?? [];
    state.axisLabel = xAxis[0]?.labelFormatter;
    state.axisTooltip = xAxis[0]?.valueFormatter;
    return <div data-testid="chart" />;
  },
}));

vi.mock("react-admin", () => ({
  useListContext: () => state,
  useResourceDefinition: () => ({ name: "WebMapService" }),
  useTranslate: () => (key: string, options?: Record<string, unknown>) =>
    options ? `${key} ${JSON.stringify(options)}` : key,
}));

beforeEach(() => {
  state.data = [];
  state.isPending = false;
  state.error = null;
  state.hasStatistics = true;
  state.series = [];
  state.days = [];
  state.axisLabel = undefined;
  state.axisTooltip = undefined;
});

describe("changesOfDays", () => {
  it("answers a day the api did not answer as a day without any change", () => {
    const days = ["2026-10-01", "2026-10-02", "2026-10-03"];
    const changes = changesOfDays(
      [{ id: 1, day: "2026-10-02", new: 4, updated: 2, deleted: 1 }],
      10,
      days,
    );
    expect(changes.map((change) => change.new)).toEqual([0, 4, 0]);
    expect(changes.map((change) => change.updated)).toEqual([0, 2, 0]);
    expect(changes.map((change) => change.deleted)).toEqual([0, 1, 0]);
  });

  it("steps the inventory back from the inventory of today", () => {
    const days = ["2026-10-01", "2026-10-02", "2026-10-03"];
    const changes = changesOfDays(
      [
        { id: 1, day: "2026-10-03", new: 1, updated: 0, deleted: 0 },
        { id: 2, day: "2026-10-02", new: 0, updated: 4, deleted: 2 },
        { id: 3, day: "2026-10-01", new: 5, updated: 0, deleted: 1 },
      ],
      10,
      days,
    );
    // the inventory of a day is the inventory which was counted after the changes
    // of that day, so the day before today carried what is left of today after
    // the addition of today, and the oldest day carried what is left of the day
    // after it after its deletions
    expect(changes.map((change) => change.total)).toEqual([11, 9, 10]);
  });

  it("answers the inventory of a resource which answers nothing as it is", () => {
    const changes = changesOfDays([], 7, ["2026-10-01", "2026-10-02"]);
    expect(changes.map((change) => change.total)).toEqual([7, 7]);
    expect(changes.map((change) => change.new)).toEqual([0, 0]);
  });
});

describe("lastDays", () => {
  it("answers the days oldest first and ends with today", () => {
    const days = lastDays(3);
    expect(days).toHaveLength(3);
    // a day of the month is asked back as the day the resource counts it, so the
    // day is expected as the day of the viewer and not as an instant of utc
    const today = new Date();
    const expected = [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, "0"),
      String(today.getDate()).padStart(2, "0"),
    ].join("-");
    expect(days[2]).toBe(expected);
    expect(days[0] < days[1]).toBe(true);
  });
});

describe("namedDays", () => {
  it("names the last day of the window and a step of the days before it", () => {
    const days = lastDays(CHANGE_DAYS);
    const named = namedDays(days);
    // the chart of a card cannot name every day of its window and must name the
    // last day, so that the window of the chart can be read
    expect(named.has(days[days.length - 1])).toBe(true);
    // every named day lies a step back from the day before it, so that the named
    // days are spread over the window and do not gather at one end of it
    const namedInOrder = days.filter((day) => named.has(day));
    expect(namedInOrder.length).toBeLessThan(days.length);
    expect(namedInOrder.length).toBeGreaterThan(1);
    const steps = namedInOrder
      .slice(1)
      .map(
        (day, index) => days.indexOf(day) - days.indexOf(namedInOrder[index]),
      );
    expect(new Set(steps).size).toBe(1);
  });

  it("names nothing of a window without days", () => {
    expect(namedDays([]).size).toBe(0);
  });
});

describe("HistoryChart", () => {
  it("says that the statistics are asked while they are not answered", () => {
    state.isPending = true;
    render(<HistoryChart total={5} />);
    expect(screen.getByText("historyChart.asking")).toBeInTheDocument();
    expect(screen.queryByTestId("chart")).not.toBeInTheDocument();
  });

  it("says that the statistics failed and never draws them as no change", () => {
    state.error = new Error("Statistics refused");
    render(<HistoryChart total={5} />);
    expect(screen.getByText("historyChart.error")).toBeInTheDocument();
    expect(
      screen.queryByText("historyChart.noStatistics"),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId("chart")).not.toBeInTheDocument();
  });

  it("says that a resource answers no statistics at all", () => {
    state.hasStatistics = false;
    render(<HistoryChart total={5} />);
    expect(screen.getByText("historyChart.noStatistics")).toBeInTheDocument();
    expect(screen.queryByTestId("chart")).not.toBeInTheDocument();
  });

  it("draws the changes stacked and the inventory which was counted after them", () => {
    const days = lastDays(30);
    state.data = [
      { id: 1, day: days[29], new: 3, updated: 2, deleted: 1 },
      { id: 2, day: days[27], new: 1, updated: 0, deleted: 0 },
    ];
    render(<HistoryChart total={10} />);
    expect(screen.getByTestId("chart")).toBeInTheDocument();

    const [inventory, added, changed, removed] = state.series;
    expect(inventory.data[29]).toBe(10);
    // the day before the additions and deletions of today carried the inventory
    // which was counted after them
    expect(inventory.data[28]).toBe(8);
    expect(added.data[29]).toBe(3);
    expect(changed.data[29]).toBe(2);
    expect(removed.data[29]).toBe(1);
    // the day which was not answered by the api changed nothing
    expect(added.data[28]).toBe(0);
    expect(added.data[26]).toBe(0);
    // the inventory is never stacked with a change, so the chart of the inventory
    // is read on its own and the amount of a day is read from the stack of changes
    expect(inventory.stack).toBeUndefined();
    expect([added.stack, changed.stack, removed.stack]).toEqual([
      "changes",
      "changes",
      "changes",
    ]);
  });

  it("names the day of every value the chart draws", () => {
    render(<HistoryChart total={0} />);
    const days = state.days;
    // the tooltip of the chart names the day of every day of the window, so a bar
    // is read as the day it changed something even when the axis has no room for it
    expect(state.axisTooltip).toBeDefined();
    const namedInTooltip = days.map((day) => state.axisTooltip!(day));
    expect(namedInTooltip.every((label) => label !== "")).toBe(true);
    // a day is named from the parts of the day of the month and not from an instant
    // of it, so the day of the window never moves into the day before it in a
    // timezone which lies behind utc
    days.forEach((day, index) =>
      expect(namedInTooltip[index]).toContain(String(Number(day.slice(8)))),
    );
    // the axis names the last day of the window and spreads the days it can name
    // over it, so the time the chart counts is readable without a label per day
    expect(state.axisLabel).toBeDefined();
    const axisLabels = days.map((day) => state.axisLabel!(day));
    expect(axisLabels[days.length - 1]).not.toBe("");
    expect(axisLabels.filter((label) => label !== "").length).toBeLessThan(
      days.length,
    );
  });

  it("names the time and the unit the chart counts in its caption", () => {
    render(<HistoryChart total={0} />);
    expect(
      screen.getByText(/"days":30,"unit":"WebMapService"/),
    ).toBeInTheDocument();
  });
});
