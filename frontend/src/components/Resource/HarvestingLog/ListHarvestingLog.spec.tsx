import type { ReactNode } from "react";
import type { RaRecord } from "react-admin";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import ListHarvestingLog from "./ListHarvestingLog";

const state = vi.hoisted(() => ({
  list: {
    filterValues: {} as Record<string, unknown>,
    displayedFilters: {} as Record<string, boolean>,
    setFilters: vi.fn(),
  },
  record: { id: 1 } as RaRecord | undefined,
}));

vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: vi.fn(() => null),
}));
vi.mock("../../Field/TruncatedTextField", () => ({
  default: () => null,
}));
vi.mock("../../Lists/CustomListActions", () => ({
  default: () => null,
}));
vi.mock("react-admin", () => ({
  useTranslate: () => (key: string, options?: Record<string, unknown>) =>
    options?.level ? `${key}:${options.level}` : key,
  useListContext: () => state.list,
  useRecordContext: () => state.record,
  BooleanField: () => null,
  DateField: () => null,
  FunctionField: () => null,
  ShowButton: () => null,
  WrapperField: ({ children }: { children?: ReactNode }) => (
    <span>{children}</span>
  ),
}));

/** renders the header the list hands into the ListGuesser */
const renderHeader = () => {
  render(<ListHarvestingLog />);
  const props = vi.mocked(ListGuesser).mock.calls.at(-1)?.[0];
  render(<>{props?.header}</>);
};

beforeEach(() => {
  state.list = {
    filterValues: {},
    displayedFilters: {},
    setFilters: vi.fn(),
  };
  state.record = { id: 1 };
});

describe("ListHarvestingLog", () => {
  it("lists the lines of one run newest first and keeps the tab unpersisted", () => {
    render(
      <ListHarvestingLog
        relatedResource={{ resource: "HarvestingJob", id: "1" }}
        refetchInterval={5000}
        storeKey={false}
      />,
    );
    const props = vi.mocked(ListGuesser).mock.calls.at(-1)?.[0];
    expect(props?.resource).toBe("HarvestingLog");
    expect(props?.relatedResource).toEqual({
      resource: "HarvestingJob",
      id: "1",
    });
    expect(props?.sort).toEqual({ field: "timestamp", order: "DESC" });
    expect(props?.refetchInterval).toBe(5000);
    expect(props?.storeKey).toBe(false);
  });
  it("asks the list which lines the caller wants and narrows the scale", () => {
    state.list.filterValues = { level__lte: 3 };
    renderHeader();
    // the facet which answers the stored filter is the lit one
    expect(screen.getByRole("button", { name: "harvestRun.logFacets.infoAndAbove" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(
      screen.getByRole("button", {
        name: "harvestRun.logFacets.warningsAndAbove",
      }),
    );
    expect(state.list.setFilters).toHaveBeenCalledWith(
      { level__lte: 2 },
      state.list.displayedFilters,
    );
    fireEvent.click(screen.getByRole("button", { name: "harvestRun.logFacets.all" }));
    expect(state.list.setFilters).toHaveBeenLastCalledWith(
      {},
      state.list.displayedFilters,
    );
  });
  it("keeps other filters while it changes the level facet", () => {
    state.list.filterValues = { other: "kept", kind: 0 };
    renderHeader();
    fireEvent.click(
      screen.getByRole("button", {
        name: "harvestRun.logFacets.infoAndAbove",
      }),
    );
    expect(state.list.setFilters).toHaveBeenLastCalledWith(
      { other: "kept", kind: 0, level__lte: 3 },
      state.list.displayedFilters,
    );
  });
  it("shows the log level the run was told to write at", () => {
    state.record = { id: 1, logLevel: 2 };
    renderHeader();
    expect(
      screen.getByText("harvestRun.runLogLevel:harvestRun.logLevels.warning"),
    ).toBeInTheDocument();
  });
  it("says nothing about a level the run does not answer", () => {
    renderHeader();
    expect(
      screen.queryByText(/harvestRun\.runLogLevel/),
    ).not.toBeInTheDocument();
  });
  it("answers the stored response per row and never its content", () => {
    render(<ListHarvestingLog />);
    const columns =
      vi.mocked(ListGuesser).mock.calls.at(-1)?.[0].columns ?? [];
    const stored = columns.find((column) => column.key === "hasExtendedDescription");
    // the flag is a field of the row; no column reads the file itself
    expect((stored?.props as { source?: string })?.source).toBe(
      "hasExtendedDescription",
    );
    expect(columns.map((column) => column.key)).not.toContain(
      "extentedDescription",
    );
  });
  it("words the level and the kind of a row as the scale gives them", () => {
    render(<ListHarvestingLog />);
    const columns =
      vi.mocked(ListGuesser).mock.calls.at(-1)?.[0].columns ?? [];
    const renderColumn = (key: string, record: RaRecord) => {
      const column = columns.find((candidate) => candidate.key === key);
      const renderCell = (
        column?.props as unknown as {
          render: (record: RaRecord) => ReactNode;
        }
      ).render;
      cleanup();
      return render(<>{renderCell(record)}</>);
    };
    renderColumn("level", { id: 1, level: 1 });
    expect(screen.getByText("harvestRun.logLevels.error")).toBeInTheDocument();
    renderColumn("kind", { id: 1, kind: 1 });
    expect(
      screen.getByText("harvestRun.logKinds.countMismatch"),
    ).toBeInTheDocument();
    renderColumn("kind", { id: 1, kind: null });
    expect(screen.queryByText(/harvestRun\.logKinds/)).not.toBeInTheDocument();
  });
});
