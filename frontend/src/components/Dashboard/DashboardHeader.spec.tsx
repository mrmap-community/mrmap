import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import de from "../../i18n/de";
import en from "../../i18n/en";
import DashboardHeader from "./DashboardHeader";

const state = vi.hoisted(() => ({ locale: "en" }));
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

const moment = Date.UTC(2026, 10, 26, 14, 30);

const header = (overrides: Partial<{
  period: 7 | 30 | 90;
  onPeriodChange: (period: 7 | 30 | 90) => void;
  onRefresh: () => void;
  refreshedAt: number | null;
}> = {}) => {
  const props = {
    period: 30 as const,
    onPeriodChange: vi.fn(),
    onRefresh: vi.fn(),
    refreshedAt: moment,
    ...overrides,
  };
  render(<DashboardHeader {...props} />);
  return props;
};

beforeEach(() => {
  state.locale = "en";
});

describe("DashboardHeader", () => {
  it("answers the translated title and description of the screen", () => {
    header();
    expect(screen.getByRole("heading", { level: 1, name: lookup("dashboard.header.title") }))
      .toBeInTheDocument();
    expect(screen.getByText(lookup("dashboard.header.description"))).toBeInTheDocument();
  });

  it("offers one period selector for the whole screen and defaults to thirty days", () => {
    const props = header();
    const selector = screen.getByRole("combobox", { name: lookup("dashboard.header.period") });
    expect(selector).toHaveTextContent("Last 30 days");
    fireEvent.mouseDown(selector);
    // the three windows of #1820 and no second selector anywhere
    expect(screen.getAllByRole("option")).toHaveLength(3);
    expect(screen.getAllByRole("option").map(option => option.textContent))
      .toEqual(["Last 7 days", "Last 30 days", "Last 90 days"]);
    fireEvent.click(screen.getByRole("option", { name: "Last 7 days" }));
    expect(props.onPeriodChange).toHaveBeenCalledWith(7);
  });

  it("answers the window of the header in the locale of the user", () => {
    state.locale = "de";
    header({ period: 90 });
    expect(screen.getByRole("combobox", { name: "Zeitraum" })).toHaveTextContent("Letzte 90 Tage");
  });

  it("names the moment of the last refresh of the whole screen", () => {
    header({ refreshedAt: moment });
    const answered = screen.getByRole("status");
    expect(answered).toHaveTextContent("Last refreshed");
    // the moment is a localized date and time, never a raw timestamp
    expect(answered).not.toHaveTextContent(String(moment));
    expect(answered).toHaveTextContent("2026");
  });

  it("says nothing about a refresh which never happened", () => {
    header({ refreshedAt: null });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("refreshes the screen on demand", () => {
    const props = header();
    fireEvent.click(screen.getByRole("button", { name: lookup("dashboard.header.refresh") }));
    expect(props.onRefresh).toHaveBeenCalledTimes(1);
  });

  it("localizes the header in German", () => {
    state.locale = "de";
    header({ refreshedAt: moment });
    expect(screen.getByRole("heading", { level: 1, name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aktualisieren" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Letzte Aktualisierung");
  });
});
