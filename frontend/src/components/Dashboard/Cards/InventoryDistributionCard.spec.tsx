import type { InventoryCountSource } from "../dashboardInventory";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import de from "../../../i18n/de";
import en from "../../../i18n/en";
import InventoryDistributionCard from "./InventoryDistributionCard";

type Slice = { id: string; label: string; value: number; color: string };
type PlotProps = {
  "aria-label"?: string;
  height: number;
  series: { id: string; data: Slice[]; innerRadius: string; valueFormatter: (v: unknown) => string }[];
};

const state = vi.hoisted(() => ({ sources: [] as InventoryCountSource[], locale: "en", chart: vi.fn() }));
const lookup = (key: string) => {
  let value: unknown = state.locale === "de" ? de : en;
  for (const part of key.split(".")) value = (value as Record<string, unknown>)?.[part];
  return typeof value === "string" ? value : key;
};

vi.mock("react-admin", () => ({
  useLocaleState: () => [state.locale],
  useTranslate: () => (key: string, options: Record<string, unknown> = {}) => {
    let message = lookup(key);
    if (message === key) message = String(options._ ?? key);
    // the plural forms react-admin counts between, which the donut needs for the
    // denominator beside its circle
    const forms = message.split(" |||| ");
    const plural = Number(options.smart_count ?? forms.length) > 1 ? 1 : 0;
    return forms[Math.min(plural, forms.length - 1)]
      .replace(/%\{(\w+)\}/g, (_all: string, name: string) => String(options[name]));
  },
}));

vi.mock("@mui/x-charts/PieChart", () => ({
  PieChart: (props: PlotProps) => {
    state.chart(props);
    return <div data-testid="donut">{props.series[0]?.data
      .map(slice => <span key={slice.id}>{slice.label}: {slice.value}</span>)}</div>;
  },
}));

const counted = (resource: string, count: number): InventoryCountSource => ({
  resource, status: "ready", count,
});
const plot = (): PlotProps => state.chart.mock.lastCall?.[0] as PlotProps;
const donut = () => screen.getByTestId("donut");
const list = () => screen.getByRole("list");

beforeEach(() => {
  state.locale = "en";
  state.sources = [counted("CatalogueService", 30), counted("ServiceMetadataRecord", 10)];
  state.chart.mockClear();
});

describe("InventoryDistributionCard", () => {
  it("shares the registered resources of the kinds which answered", () => {
    render(<InventoryDistributionCard sources={state.sources} />);
    expect(donut()).toHaveTextContent("Catalogue Service: 30");
    expect(donut()).toHaveTextContent("Service metadata records: 10");
    expect(plot().series[0].innerRadius).toBe("55%");
    expect(screen.getByRole("heading", { name: lookup("dashboard.distribution.title") }))
      .toBeInTheDocument();
  });

  it("says the denominator beside the circle and never the whole deployment", () => {
    render(<InventoryDistributionCard sources={state.sources} />);
    expect(screen.getByText("40 registered resources of 2 kinds counted")).toBeInTheDocument();
  });

  it("answers the exact count and percentage of every kind in a list", () => {
    render(<InventoryDistributionCard sources={state.sources} />);
    expect(within(list()).getAllByRole("listitem")).toHaveLength(2);
    expect(list()).toHaveTextContent("Catalogue Service: 30");
    expect(list()).toHaveTextContent("75%");
    expect(list()).toHaveTextContent("Service metadata records: 10");
    expect(list()).toHaveTextContent("25%");
  });

  it("names the missing count instead of enlarging the shares of the others", () => {
    state.sources = [
      counted("CatalogueService", 30),
      { resource: "FeatureType", status: "error" },
    ];
    render(<InventoryDistributionCard sources={state.sources} />);
    expect(donut()).toHaveTextContent("Catalogue Service: 30");
    expect(donut()).not.toHaveTextContent("Feature types");
    // the denominator stays the sum of what answered, and the gap is named
    expect(screen.getByText("30 registered resource of 1 kind counted")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Feature types");
    expect(screen.getByRole("status")).toHaveTextContent("cannot answer its count right now");
  });

  it("groups the unreadable small shares into one arc and offers the exact breakdown", () => {
    state.sources = [
      counted("CatalogueService", 70),
      counted("Layer", 2),
      counted("FeatureType", 2),
      counted("WebMapService", 1),
    ];
    render(<InventoryDistributionCard sources={state.sources} />);
    // the circle groups the three small kinds ...
    expect(donut()).toHaveTextContent("Other: 5");
    expect(donut()).not.toHaveTextContent("Feature types");
    // ... while the list beside it keeps every exact count and percentage
    expect(within(list()).getAllByRole("listitem")).toHaveLength(4);
    expect(list()).toHaveTextContent("Feature types: 2");
    expect(list()).toHaveTextContent("Web Map Services: 1");
    fireEvent.click(screen.getByRole("button", {
      name: lookup("dashboard.distribution.explain").replace("%{resources}", "3"),
    }));
    expect(donut()).not.toHaveTextContent("Other");
    expect(donut()).toHaveTextContent("Feature types: 2");
    fireEvent.click(screen.getByRole("button", {
      name: lookup("dashboard.distribution.group").replace("%{threshold}", "5"),
    }));
    expect(donut()).toHaveTextContent("Other: 5");
  });

  it("leaves the circle ungrouped while only one share is small", () => {
    state.sources = [counted("CatalogueService", 70), counted("Layer", 2)];
    render(<InventoryDistributionCard sources={state.sources} />);
    expect(donut()).not.toHaveTextContent("Other");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("counts every kind of the inventory, also the ones without any history", () => {
    // the donut answers an inventory and not a history: a resource the
    // statistics of #1817 cannot prove still counts today
    state.sources = [counted("WebMapService", 5), counted("WebFeatureService", 3)];
    render(<InventoryDistributionCard sources={state.sources} />);
    expect(donut()).toHaveTextContent("Web Map Services: 5");
    expect(donut()).toHaveTextContent("Web Feature Services: 3");
  });

  it("answers a deployment without resources as empty and not as broken", () => {
    state.sources = [counted("CatalogueService", 0), counted("Layer", 0)];
    render(<InventoryDistributionCard sources={state.sources} />);
    expect(state.chart).toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent(lookup("dashboard.distribution.empty"));
    expect(screen.getByText("0 registered resources of 2 kinds counted")).toBeInTheDocument();
  });

  it.each(["partial", "error", "loading", "unsupported"] as const)(
    "answers the %s state of the whole card when no count answered", status => {
      state.sources = [{ resource: "CatalogueService", status }];
      render(<InventoryDistributionCard sources={state.sources} />);
      expect(state.chart).not.toHaveBeenCalled();
      expect(screen.getByRole("status")).toBeInTheDocument();
    });

  it("answers a screen without any inventory at all without a circle", () => {
    render(<InventoryDistributionCard sources={[]} />);
    expect(state.chart).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("counts the values of the circle in the locale of the user and names its arcs", () => {
    state.locale = "de";
    state.sources = [counted("CatalogueService", 1234)];
    render(<InventoryDistributionCard sources={state.sources} />);
    expect(screen.getByRole("heading", { name: "Ressourcenverteilung" })).toBeInTheDocument();
    expect(plot().series[0].valueFormatter({ value: 1234 })).toBe("1.234");
    expect(donut()).toHaveTextContent("Katalogdienste: 1234");
    expect(screen.getByText("1.234 registrierte Ressource aus 1 Art gezählt")).toBeInTheDocument();
  });
});
