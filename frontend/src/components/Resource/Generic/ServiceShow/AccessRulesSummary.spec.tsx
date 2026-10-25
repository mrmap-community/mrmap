import type { ReactNode } from "react";
import { BasenameContextProvider, type RaRecord } from "react-admin";
import { MemoryRouter } from "react-router-dom";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccessRulesSummary from "./AccessRulesSummary";

const state = vi.hoisted(() => ({
  records: [] as RaRecord[],
  error: false,
  isPending: false,
}));
vi.mock("react-admin", async () => ({
  ...(await vi.importActual<typeof import("react-admin")>("react-admin")),
  useTranslate: () => (key: string, options?: { count?: number }) =>
    options?.count === undefined ? key : `${key} ${options.count}`,
  Loading: () => <span>Loading</span>,
  useListContext: () => ({
    data: state.records,
    isPending: state.isPending,
    error: state.error,
    refetch: vi.fn(),
  }),
}));
vi.mock("../../../MapContainer/GeoJsonMap", () => ({
  default: ({ children }: { children?: ReactNode }) => (
    <div data-testid="geojson-map">{children}</div>
  ),
}));
vi.mock("../../../Input/FeatureGroupEditor", () => ({
  default: ({ geoJson }: { geoJson: { features: unknown[] } }) => (
    <div data-testid="areas">{geoJson.features.length}</div>
  ),
}));

const restricted = {
  id: 1,
  allowedArea: { type: "MultiPolygon", coordinates: [] },
  operations: [{ id: 7, stringRepresentation: "GetMap" }],
  allowedGroups: [{ id: 3, name: "editors" }],
  securedLayers: [{ id: 9, title: "base" }],
};
const open = {
  id: 2,
  allowedArea: null,
  operations: [{ id: 7, stringRepresentation: "GetMap" }],
  allowedGroups: [],
  securedLayers: [{ id: 9, title: "base" }],
};

const show = () =>
  render(
    <MemoryRouter>
      <BasenameContextProvider basename="/WebMapService/4/show">
        <AccessRulesSummary
          ruleResource="AllowedWebMapServiceOperation"
          serviceId="4"
        />
      </BasenameContextProvider>
    </MemoryRouter>,
  );

beforeEach(() => {
  state.records = [];
  state.error = false;
  state.isPending = false;
});

describe("access rules summary", () => {
  it("names groups, operations and content of every configured rule", () => {
    state.records = [restricted];
    show();
    expect(screen.getByText("GetMap")).toBeInTheDocument();
    expect(screen.getByText("editors")).toBeInTheDocument();
    expect(screen.getByText("base")).toBeInTheDocument();
    expect(screen.getByText("accessRules.restricted")).toBeInTheDocument();
  });

  it("renders feature types from the WFS list context", () => {
    state.records = [{
      ...restricted,
      securedFeatureTypes: [{ id: 12, title: "roads" }],
    }];
    render(
      <MemoryRouter>
        <AccessRulesSummary
          ruleResource="AllowedWebFeatureServiceOperation"
          serviceId="5"
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("roads")).toBeInTheDocument();
    expect(screen.getByText("accessRules.featureTypes")).toBeInTheDocument();
    expect(screen.queryByText("base")).not.toBeInTheDocument();
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });

  it("collapses long layer lists and expands each rule independently without selecting it", () => {
    const layers = Array.from({ length: 20 }, (_, id) => ({ id, title: `Layer ${id}` }));
    state.records = [restricted, { ...open, securedLayers: layers }];
    show();
    expect(screen.getByText("Layer 2")).toBeInTheDocument();
    expect(screen.queryByText("Layer 3")).not.toBeInTheDocument();
    const expand = screen.getByRole("button", { name: "accessRules.showMore 17" });
    expect(expand).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(expand);
    expect(screen.getByText("Layer 19")).toBeInTheDocument();
    expect(screen.getByTestId("geojson-map")).toBeInTheDocument();
    const collapse = screen.getByRole("button", { name: "accessRules.showLess" });
    expect(collapse).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(collapse);
    expect(screen.queryByText("Layer 3")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "accessRules.showLess" })).not.toBeInTheDocument();
  });

  it("explains rules without groups and without an allowed area", () => {
    state.records = [open];
    show();
    expect(screen.getByText("accessRules.allGroups")).toBeInTheDocument();
    expect(
      screen.getByRole("alert").textContent,
    ).toContain("accessRules.unrestrictedExplanation");
    expect(screen.queryByTestId("geojson-map")).not.toBeInTheDocument();
  });

  it("maps only the area of the selected rule and follows row clicks", () => {
    state.records = [restricted, open];
    show();
    expect(screen.getByTestId("geojson-map")).toBeInTheDocument();
    expect(screen.getByTestId("areas")).toHaveTextContent("1");
    fireEvent.click(screen.getAllByRole("row")[2]);
    expect(
      screen.queryByTestId("geojson-map"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("alert").textContent,
    ).toContain("accessRules.unrestrictedExplanation");
  });

  it("links every entry to the rule editor", () => {
    state.records = [restricted];
    show();
    expect(screen.getByRole("link", { name: "accessRules.edit" })).toHaveAttribute(
      "href",
      "/WebMapService/4/show/AllowedWebMapServiceOperation/1/edit",
    );
  });

  it("shows the list loading state", () => {
    state.isPending = true;
    show();
    expect(screen.getByText("Loading")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("separates loading, empty and error states", () => {
    const view = show();
    expect(screen.getByText("accessRules.empty")).toBeInTheDocument();
    state.error = true;
    view.rerender(
      <MemoryRouter>
        <BasenameContextProvider basename="/WebMapService/4/show">
          <AccessRulesSummary
            ruleResource="AllowedWebMapServiceOperation"
            serviceId="4"
          />
        </BasenameContextProvider>
      </MemoryRouter>,
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "accessRules.loadError",
    );
  });
});
