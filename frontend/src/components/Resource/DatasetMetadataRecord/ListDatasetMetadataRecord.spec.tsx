import { fireEvent, render, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { describe, expect, it, vi } from "vitest";
import { DatasetExplorer } from "./ListDatasetMetadataRecord";
const context = vi.hoisted(() => ({
  data: [
    {
      id: "one",
      title: "Covered dataset",
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
    { id: "two", title: "Dataset without bounds" },
  ],
  total: 2,
  isPending: false,
}));
vi.mock("react-admin", () => ({
  useListContext: () => context,
  useTranslate: () => (key: string) => key,
  RecordContextProvider: ({ children }: PropsWithChildren) => children,
  DateField: () => null,
  ShowButton: () => <button>Show</button>,
  EditButton: () => <button>Edit</button>,
  SortButton: () => null,
}));
vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: () => null,
}));
vi.mock("../../Lists/CustomListActions", () => ({ default: () => null }));
vi.mock("./DatasetCoverageMap", () => ({
  default: ({
    selected,
    onSelect,
  }: {
    selected?: string;
    onSelect: (id: string) => void;
  }) => (
    <div data-testid="coverage-map">
      {selected}
      <button onClick={() => onSelect("one")}>Select extent</button>
    </div>
  ),
}));
describe("dataset explorer", () => {
  it("keeps records without coverage visible", () => {
    render(<DatasetExplorer />);
    expect(screen.getByText("Dataset without bounds")).toBeInTheDocument();
    expect(
      screen.getByText("datasetExplorer.missingCoverage"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("coverage-map")).toBeInTheDocument();
  });
  it("links selection between results and map", () => {
    render(<DatasetExplorer />);
    fireEvent.click(screen.getByText("Dataset without bounds"));
    expect(screen.getByTestId("coverage-map")).toHaveTextContent("two");
    fireEvent.click(screen.getByText("Select extent"));
    expect(screen.getByTestId("coverage-map")).toHaveTextContent("one");
  });
  it("switches between list, map and split", () => {
    render(<DatasetExplorer />);
    fireEvent.click(
      screen.getByRole("button", { name: "datasetExplorer.map" }),
    );
    expect(screen.queryByText("Covered dataset")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "datasetExplorer.list" }),
    );
    expect(screen.queryByTestId("coverage-map")).not.toBeInTheDocument();
    expect(screen.getByText("Covered dataset")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "datasetExplorer.split" }),
    );
    expect(screen.getByTestId("coverage-map")).toBeInTheDocument();
  });
});
