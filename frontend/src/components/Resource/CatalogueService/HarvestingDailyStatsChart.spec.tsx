import { useListContext, useTranslate } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import i18nProvider from "../../../providers/i18nProvider";
import HarvestingDailyStatsChart from "./HarvestingDailyStatsChart";

import "@testing-library/jest-dom/vitest";

vi.mock("react-admin", () => ({
  useListContext: vi.fn(),
  useTranslate: vi.fn(),
}));

// The chart container is replaced by the labels it receives: the contract
// asserted here is which series and axis labels the chart draws (#1085).
vi.mock("../../MUI/GradientChartsContainer", () => ({
  default: ({
    series,
    xAxis,
    yAxis,
  }: {
    series: { label: string }[];
    xAxis: { label: string }[];
    yAxis: { label: string }[];
  }) => (
    <div data-testid="chart">
      {series.map(s => s.label).join(",")}|{xAxis[0].label}|{yAxis[0].label}
    </div>
  ),
}));

// The base fetches the daily statistics; the list context stands in for it.
vi.mock("../Generic/History/HistoryListBase", () => ({
  default: ({ children }: { children: import("react").ReactNode }) => <>{children}</>,
}));

const day = new Date().toISOString().split("T")[0];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useListContext, { partial: true }).mockReturnValue({
    data: [{ id: day, day, new: 1, updated: 2, existed: 3 }],
  });
});

describe.each([
  { locale: "en", records: "Records", axis: "Day" },
  { locale: "de", records: "Datensätze", axis: "Tag" },
])("harvesting daily stats chart in $locale", ({ locale, records, axis }) => {
  beforeEach(async () => {
    await i18nProvider.changeLocale(locale);
    vi.mocked(useTranslate).mockReturnValue(i18nProvider.translate);
  });

  it("names its single series and its axis in the active language", () => {
    render(<HarvestingDailyStatsChart />);

    // Exactly one series: nothing is collected that the chart would hide.
    expect(screen.getByTestId("chart")).toHaveTextContent(
      `${records}|${axis}|${records}`,
    );
    expect(screen.getByTestId("chart")).not.toHaveTextContent(/deleted|new|updated|existed/);
  });
});
