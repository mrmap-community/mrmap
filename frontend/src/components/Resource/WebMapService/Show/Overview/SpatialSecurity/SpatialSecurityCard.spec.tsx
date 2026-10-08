import { act, render, screen } from "@testing-library/react";
import { BasenameContextProvider, type RaRecord } from "react-admin";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SpatialSecurityCard from "./SpatialSecurityCard";

const state = vi.hoisted(() => ({
  records: [] as RaRecord[],
  error: false,
  hasNextPage: false,
}));
vi.mock("react-admin", async () => ({
  ...(await vi.importActual<typeof import("react-admin")>("react-admin")),
  useRecordContext: () => ({ id: "service" }),
  useTranslate: () => (key: string, options?: { count: number }) =>
    options ? `${key}: ${options.count}` : key,
  Loading: () => <span>Loading configuration</span>,
}));
vi.mock("./useCompleteList", () => ({
  default: () => ({
    ...state,
    isPending: false,
    isFetchingNextPage: false,
    refetch: vi.fn(),
  }),
}));

const show = () =>
  render(
    <MemoryRouter>
      <BasenameContextProvider basename="/WebMapService/service/show">
        <SpatialSecurityCard />
      </BasenameContextProvider>
    </MemoryRouter>,
  );
const rule = {
  id: 1,
  allowedArea: { type: "MultiPolygon", coordinates: [] },
  securedLayers: [{ id: 3 }],
  allowedGroups: [{ id: 1 }],
};
beforeEach(() => {
  state.records = [];
  state.error = false;
  state.hasNextPage = false;
});

describe("spatial security overview", () => {
  it("summarizes configured spatial rules and deduplicates layers and groups", () => {
    state.records = [
      rule,
      { ...rule, id: 2 },
      { ...rule, id: 3, allowedArea: null },
    ];
    show();
    expect(screen.getByText("spatialSecurity.configured")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getAllByText("1")).toHaveLength(2);
    expect(
      screen.getByText("spatialSecurity.unrestrictedRules: 1"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(
      screen.getByRole("link", { name: "spatialSecurity.testPolicies" }),
    ).toHaveAttribute(
      "href",
      "/WebMapService/service/show/AllowedWebMapServiceOperation",
    );
  });
  it("distinguishes no rules from access rules without polygons", () => {
    const view = show();
    expect(screen.getByText("spatialSecurity.noRules")).toBeInTheDocument();
    state.records = [{ ...rule, allowedArea: null }];
    view.rerender(
      <MemoryRouter>
        <BasenameContextProvider basename="/WebMapService/service/show">
          <SpatialSecurityCard />
        </BasenameContextProvider>
      </MemoryRouter>,
    );
    expect(
      screen.getByText("spatialSecurity.noSpatialRules"),
    ).toBeInTheDocument();
  });
  it("identifies rules applying to every group", () => {
    state.records = [{ ...rule, allowedGroups: [] }];
    show();
    expect(screen.getByText("spatialSecurity.allGroups")).toBeInTheDocument();
  });
  it("does not display incomplete counts", () => {
    state.records = [rule];
    state.hasNextPage = true;
    show();
    expect(screen.getByText("Loading configuration")).toBeInTheDocument();
    expect(
      screen.queryByText("spatialSecurity.configured"),
    ).not.toBeInTheDocument();
  });
  it("explains metric counts in keyboard-accessible tooltips", async () => {
    state.records = [rule];
    show();
    act(() =>
      screen.getByText("spatialSecurity.layerCount").parentElement!.focus(),
    );
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      "spatialSecurity.layerHint",
    );
  });
  it("reports loading failures", () => {
    state.error = true;
    show();
    expect(screen.getByText("spatialSecurity.loadError")).toBeInTheDocument();
    expect(
      screen.queryByText("spatialSecurity.noRules"),
    ).not.toBeInTheDocument();
  });
});
