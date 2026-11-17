import type { PropsWithChildren } from "react";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ServiceExplorer, { ServiceResults } from "./ServiceExplorer";
const context = vi.hoisted(() => ({
  data: [
    {
      id: "one",
      title: "Public service",
      isActive: true,
      allowedActions: [],
      hits: 42,
      version: "1.3.0",
      elementCount: 5,
    },
  ],
  total: 1,
  isPending: false,
  filterValues: { search: "ortho" },
  displayedFilters: {},
  setFilters: vi.fn(),
}));
vi.mock("../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: () => [],
}));
vi.mock("react-admin", () => ({
  useListContext: () => context,
  useTranslate: () => (key: string) => key,
  ResourceContextProvider: ({ children }: PropsWithChildren) => children,
  RecordContextProvider: ({ children }: PropsWithChildren) => children,
  DateField: () => null,
  SortButton: () => null,
  SearchInput: () => null,
  ShowButton: () => <button>Show</button>,
  EditButton: () => <button>Edit</button>,
}));
vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: ({
    resource,
    queryOptions,
  }: {
    resource: string;
    queryOptions?: { meta?: { jsonApiParams?: Record<string, string> } };
  }) => (
    <div
      data-testid="queried-resource"
      data-fields={queryOptions?.meta?.jsonApiParams?.[`fields[${resource}]`]}
    >
      {resource}
    </div>
  ),
}));
vi.mock("../../Lists/CustomListActions", () => ({ default: () => null }));
vi.mock("../WebMapService/Button/ListActions", () => ({
  default: () => <button>Viewer</button>,
}));
vi.mock("../CatalogueService/CatalogueServiceList", () => ({
  HarvestButton: () => <button>Harvest</button>,
}));
vi.mock("../Generic/Explorer/CoverageMap", () => ({
  default: ({ onSearchArea }: { onSearchArea: (geometry: string) => void }) => (
    <button onClick={() => onSearchArea("viewport")}>Search area</button>
  ),
}));

describe("service explorer", () => {
  it("switches protocol on the same screen", () => {
    render(<ServiceExplorer />);
    expect(screen.getByTestId("queried-resource")).toHaveTextContent(
      "WebMapService",
    );
    // the row's edit and show buttons ask the auth provider, which reads
    // the permission hint of #738 - so the screen has to request the field
    expect(screen.getByTestId("queried-resource")).toHaveAttribute(
      "data-fields",
      expect.stringContaining("allowed_actions"),
    );
    fireEvent.click(screen.getByRole("tab", { name: "WFS" }));
    expect(screen.getByTestId("queried-resource")).toHaveTextContent(
      "WebFeatureService",
    );
    fireEvent.click(screen.getByRole("tab", { name: "CSW" }));
    expect(screen.getByTestId("queried-resource")).toHaveTextContent(
      "CatalogueService",
    );
  });
  it("shows services without extent, signals and viewer buttons", () => {
    render(<ServiceResults resource="WebMapService" />);
    expect(screen.getByText("Public service")).toBeInTheDocument();
    expect(
      screen.getByText("serviceExplorer.missingCoverage"),
    ).toBeInTheDocument();
    expect(screen.getByText("serviceExplorer.active")).toBeInTheDocument();
    expect(screen.getByText("1.3.0")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Viewer" })).toBeInTheDocument();
    // whether the row may be edited is no longer the screen's question: the
    // real EditButton asks the auth provider, which judges the row by its
    // allowedActions hint - pinned in providers/permissions.spec.ts (#738).
    // The mocked button stands in for that gated button either way.
    expect(screen.getByRole("button", { name: "Show" })).toBeInTheDocument();
  });
  it("retains edit and harvest actions for a catalogue", () => {
    render(<ServiceResults resource="CatalogueService" />);
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Harvest" })).toBeInTheDocument();
    expect(screen.getByText("serviceExplorer.catalogueScope")).toBeInTheDocument();
  });
  it("filters the whole collection by viewport, retaining text filters", () => {
    render(<ServiceResults resource="WebMapService" />);
    fireEvent.click(screen.getByRole("button", { name: "Search area" }));
    expect(context.setFilters).toHaveBeenCalledWith(
      { search: "ortho", bbox_lat_lon__intersects: "viewport" },
      {},
    );
  });
});
