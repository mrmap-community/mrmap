import type { ReactNode } from "react";
import { BasenameContextProvider, type RaRecord } from "react-admin";
import { MemoryRouter } from "react-router-dom";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccessRulesSummary from "./AccessRulesSummary";

const state = vi.hoisted(() => ({
  records: [] as RaRecord[],
  error: false,
  options: undefined as Record<string, unknown> | undefined,
}));
vi.mock("react-admin", async () => ({
  ...(await vi.importActual<typeof import("react-admin")>("react-admin")),
  useTranslate: () => (key: string) => key,
  Loading: () => <span>Loading</span>,
}));
vi.mock("./useCompleteList", () => ({
  default: (resource: string, serviceId: unknown, options: Record<string, unknown>) => {
    state.options = { resource, serviceId, ...options };
    return {
      ...state,
      isPending: false,
      isFetchingNextPage: false,
      hasNextPage: false,
      refetch: vi.fn(),
    };
  },
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
  state.options = undefined;
});

describe("access rules summary", () => {
  it("asks the api for the related rules with readable relationships", () => {
    show();
    expect(state.options).toMatchObject({
      resource: "AllowedWebMapServiceOperation",
      serviceId: "4",
      serviceResource: "WebMapService",
      jsonApiParams: {
        include: "operations,allowedGroups,securedLayers",
      },
    });
  });

  it("names groups, operations and content of every configured rule", () => {
    state.records = [restricted];
    show();
    expect(screen.getByText("GetMap")).toBeInTheDocument();
    expect(screen.getByText("editors")).toBeInTheDocument();
    expect(screen.getByText("base")).toBeInTheDocument();
    expect(screen.getByText("accessRules.restricted")).toBeInTheDocument();
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
