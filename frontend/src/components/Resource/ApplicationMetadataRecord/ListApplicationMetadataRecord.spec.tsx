import type { ListGuesserProps } from "../../../jsonapi/components/ListGuesser";

import type { PropsWithChildren } from "react";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ListApplicationMetadataRecord from "./ListApplicationMetadataRecord";

const context = vi.hoisted(() => ({
  data: [
    {
      id: "one",
      title: "Covered application metadata",
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
    { id: "two", title: "Application metadata without bounds" },
  ],
  total: 2,
  isPending: false,
  filterValues: {} as Record<string, unknown>,
  displayedFilters: {},
  setFilters: vi.fn(),
}));
const definitions = vi.hoisted(() => ({ hasShow: true }));
vi.mock("react-admin", () => ({
  useListContext: () => context,
  useResourceDefinition: () => definitions,
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
  definitions.hasShow = true;
});

describe("application metadata explorer", () => {
  it("uses the application metadata resource and asks the list fields of the api", () => {
    render(<ListApplicationMetadataRecord />);
    expect(screen.getByTestId("resource")).toHaveTextContent(
      "ApplicationMetadataRecord",
    );
    expect(screen.getByTestId("query-options")).toHaveTextContent(
      '"fields[ApplicationMetadataRecord]":"id,title,abstract,bounding_geometry,date_stamp,is_broken,insufficient_quality,licence"',
    );
    expect(
      screen.getByText("applicationMetadataExplorer.title"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Application metadata without bounds"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("applicationMetadataExplorer.missingCoverage"),
    ).toBeInTheDocument();
  });
  it("links selection between results and map and supports all three views", () => {
    render(<ListApplicationMetadataRecord />);
    fireEvent.click(screen.getByText("Application metadata without bounds"));
    expect(screen.getByTestId("coverage-map")).toHaveTextContent("two");
    fireEvent.click(screen.getByText("Select extent"));
    expect(screen.getByTestId("coverage-map")).toHaveTextContent("one");
    fireEvent.click(
      screen.getByRole("button", {
        name: "applicationMetadataExplorer.map",
      }),
    );
    expect(
      screen.queryByText("Covered application metadata"),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "applicationMetadataExplorer.list",
      }),
    );
    expect(screen.queryByTestId("coverage-map")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "applicationMetadataExplorer.split",
      }),
    );
    expect(screen.getByTestId("coverage-map")).toBeInTheDocument();
  });
  it("offers the detail screen only where the resource has one", () => {
    render(<ListApplicationMetadataRecord />);
    expect(screen.getAllByRole("button", { name: "Show" })).toHaveLength(2);
  });
  it("leaves the result rows actionless without a show screen", () => {
    definitions.hasShow = false;
    render(<ListApplicationMetadataRecord />);
    expect(
      screen.queryByRole("button", { name: "Show" }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("coverage-map")).toHaveAttribute(
      "data-show-details",
      "false",
    );
  });
  it("searches the viewport while retaining other filters", () => {
    context.filterValues = { search: "wms" };
    render(<ListApplicationMetadataRecord />);
    fireEvent.click(screen.getByRole("button", { name: "Search area" }));
    expect(context.setFilters).toHaveBeenCalledWith(
      { search: "wms", bounding_geometry__intersects: "viewport" },
      {},
    );
  });
  it("clears the viewport filter without clearing the text search", () => {
    context.filterValues = {
      search: "wms",
      bounding_geometry__intersects: "viewport",
    };
    render(<ListApplicationMetadataRecord />);
    fireEvent.click(
      screen.getByRole("button", {
        name: "applicationMetadataExplorer.clearArea",
      }),
    );
    expect(context.setFilters).toHaveBeenCalledWith({ search: "wms" }, {});
  });
});
