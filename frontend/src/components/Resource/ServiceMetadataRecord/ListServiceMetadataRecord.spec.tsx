import type { ListGuesserProps } from "../../../jsonapi/components/ListGuesser";

import type { PropsWithChildren } from "react";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ListServiceMetadataRecord from "./ListServiceMetadataRecord";

const context = vi.hoisted(() => ({
  data: [
    {
      id: "one",
      title: "Covered service metadata",
      boundingGeometry: {
        type: "Polygon",
        coordinates: [
          [
            [6, 49],
            [7, 49],
            [7, 50],
            [6, 49],
          ],
        ],
      },
    },
    { id: "two", title: "Service metadata without bounds" },
  ],
  total: 2,
  isPending: false,
  filterValues: {} as Record<string, unknown>,
  displayedFilters: {},
  setFilters: vi.fn(),
}));
vi.mock("react-admin", () => ({
  useListContext: () => context,
  useResourceDefinition: () => ({ hasShow: false }),
  useTranslate: () => (key: string) => key,
  RecordContextProvider: ({ children }: PropsWithChildren) => children,
  DateField: () => null,
  SearchInput: () => null,
  ShowButton: () => <button>Show</button>,
  EditButton: () => <button>Edit</button>,
  SortButton: () => null,
}));
vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: ({ listContent, resource, queryOptions }: ListGuesserProps) => (
    <>
      <div data-testid="resource">{resource}</div>
      <div data-testid="query-options">{JSON.stringify(queryOptions)}</div>
      {listContent}
    </>
  ),
}));
vi.mock("../../Lists/CustomListActions", () => ({ default: () => null }));
vi.mock("../Generic/Explorer/MetadataIndicators", () => ({
  MetadataFacets: () => null,
  MetadataIndicators: () => null,
}));
vi.mock("../Generic/Explorer/CoverageMap", () => ({
  default: ({
    selected,
    onSelect,
    onSearchArea,
    showDetails,
  }: {
    selected?: string;
    onSelect: (id: string) => void;
    onSearchArea: (geometry: string) => void;
    showDetails: boolean;
  }) => (
    <div data-testid="coverage-map" data-show-details={showDetails}>
      {selected}
      <button onClick={() => onSelect("one")}>Select extent</button>
      <button onClick={() => onSearchArea("viewport")}>Search area</button>
    </div>
  ),
}));

beforeEach(() => {
  context.filterValues = {};
  context.setFilters.mockClear();
});

describe("service metadata explorer", () => {
  it("uses the service metadata resource and retains records without coverage", () => {
    render(<ListServiceMetadataRecord />);
    expect(screen.getByTestId("resource")).toHaveTextContent(
      "ServiceMetadataRecord",
    );
    expect(screen.getByTestId("query-options")).toHaveTextContent(
      '"fields[ServiceMetadataRecord]":"id,title,abstract,bounding_geometry,date_stamp,is_broken,insufficient_quality,licence"',
    );
    expect(
      screen.getByText("serviceMetadataExplorer.title"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Service metadata without bounds"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("serviceMetadataExplorer.missingCoverage"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Show" }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("coverage-map")).toHaveAttribute(
      "data-show-details",
      "false",
    );
  });
  it("links selection between results and map and supports all three views", () => {
    render(<ListServiceMetadataRecord />);
    fireEvent.click(screen.getByText("Service metadata without bounds"));
    expect(screen.getByTestId("coverage-map")).toHaveTextContent("two");
    fireEvent.click(screen.getByText("Select extent"));
    expect(screen.getByTestId("coverage-map")).toHaveTextContent("one");
    fireEvent.click(
      screen.getByRole("button", { name: "serviceMetadataExplorer.map" }),
    );
    expect(
      screen.queryByText("Covered service metadata"),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "serviceMetadataExplorer.list" }),
    );
    expect(screen.queryByTestId("coverage-map")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "serviceMetadataExplorer.split" }),
    );
    expect(screen.getByTestId("coverage-map")).toBeInTheDocument();
  });
  it("searches the viewport while retaining other filters", () => {
    context.filterValues = { search: "ortho" };
    render(<ListServiceMetadataRecord />);
    fireEvent.click(screen.getByRole("button", { name: "Search area" }));
    expect(context.setFilters).toHaveBeenCalledWith(
      { search: "ortho", bounding_geometry__intersects: "viewport" },
      {},
    );
  });
  it("clears the viewport filter without clearing the text search", () => {
    context.filterValues = {
      search: "ortho",
      bounding_geometry__intersects: "viewport",
    };
    render(<ListServiceMetadataRecord />);
    fireEvent.click(
      screen.getByRole("button", { name: "serviceMetadataExplorer.clearArea" }),
    );
    expect(context.setFilters).toHaveBeenCalledWith({ search: "ortho" }, {});
  });
});
