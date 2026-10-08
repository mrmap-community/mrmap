import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useGetList, useGetMany, type RaRecord } from "react-admin";
import SchemaAutocompleteInput from "./SchemaAutocompleteInput";

const state = vi.hoisted(() => ({
  value: undefined as
    | string
    | RaRecord
    | { id: null | undefined }
    | (RaRecord | null)[]
    | null
    | undefined,
  search: [] as RaRecord[],
  fetched: undefined as RaRecord[] | undefined,
}));
vi.mock("react-hook-form", () => ({ useWatch: () => state.value }));
vi.mock("../hooks/useSchemaRecordRepresentation", () => ({
  default: () => (record: RaRecord) => record.stringRepresentation,
}));
vi.mock("react-admin", () => {
  const Input = ({
    choices,
    onOpen,
    onClose,
    setFilter,
  }: {
    choices: RaRecord[];
    onOpen: () => void;
    onClose: () => void;
    setFilter: (search: string) => void;
  }) => (
    <>
      <button onClick={() => onOpen()}>Open</button>
      <button onClick={() => onClose()}>Close</button>
      <input
        aria-label="Search"
        onChange={(event) => setFilter(event.target.value)}
      />
      <select aria-label="Operations">
        {choices.map((choice) => (
          <option key={choice.id} value={choice.id}>
            {choice.stringRepresentation}
          </option>
        ))}
      </select>
    </>
  );
  return {
    AutocompleteArrayInput: Input,
    AutocompleteInput: Input,
    useRecordContext: () => undefined,
    useGetList: vi.fn(() => ({ data: state.search })),
    useGetMany: vi.fn(() => ({ data: state.fetched })),
  };
});
beforeEach(() => {
  vi.clearAllMocks();
  state.value = undefined;
  state.fetched = undefined;
  state.search = [
    { id: 20, stringRepresentation: "GetMap" },
    { id: 21, stringRepresentation: "GetFeatureInfo" },
  ];
});
describe("SchemaAutocompleteInput choices", () => {
  it.each(["", { id: "" }, { id: null }, { id: undefined }])(
    "does not fabricate an empty choice for %s",
    (value) => {
      state.value = value;
      state.search = [];
      render(
        <SchemaAutocompleteInput
          reference="WebMapServiceOperation"
          source="operation"
        />,
      );
      expect(screen.queryAllByRole("option")).toHaveLength(0);
      expect(useGetMany).toHaveBeenLastCalledWith(
        "WebMapServiceOperation",
        expect.objectContaining({ ids: [] }),
        { enabled: false },
      );
    },
  );
  it.each([true, false])(
    "clears a selection without fetching a null ID with multiple=%s",
    (multiple) => {
      state.value = { id: 99, stringRepresentation: "Selected" };
      const { rerender } = render(
        <SchemaAutocompleteInput
          reference="WebMapServiceOperation"
          source="operations"
          multiple={multiple ? true : undefined}
        />,
      );
      state.value = null;
      rerender(
        <SchemaAutocompleteInput
          reference="WebMapServiceOperation"
          source="operations"
          multiple={multiple ? true : undefined}
        />,
      );
      expect(
        screen.queryByRole("option", { name: "Selected" }),
      ).not.toBeInTheDocument();
      expect(screen.getAllByRole("option")).toHaveLength(2);
      expect(useGetMany).toHaveBeenLastCalledWith(
        "WebMapServiceOperation",
        expect.objectContaining({ ids: [] }),
        { enabled: false },
      );
    },
  );
  it("ignores null entries within a multiple selection", () => {
    state.value = [null, { id: 99, stringRepresentation: "Selected" }];
    render(
      <SchemaAutocompleteInput
        reference="WebMapServiceOperation"
        source="operations"
        multiple
      />,
    );
    expect(screen.getAllByRole("option")).toHaveLength(3);
    expect(
      screen.getByRole("option", { name: "Selected" }),
    ).toBeInTheDocument();
  });
  it.each([true, false])(
    "fetches choices when opened without search with multiple=%s",
    (multiple) => {
      const onOpen = vi.fn();
      const onClose = vi.fn();
      render(
        <SchemaAutocompleteInput
          reference="WebMapServiceOperation"
          source="operations"
          multiple={multiple ? true : undefined}
          onOpen={onOpen}
          onClose={onClose}
        />,
      );
      expect(useGetList).toHaveBeenLastCalledWith(
        "WebMapServiceOperation",
        expect.anything(),
        { enabled: false },
      );
      fireEvent.click(screen.getByText("Open"));
      expect(useGetList).toHaveBeenLastCalledWith(
        "WebMapServiceOperation",
        expect.objectContaining({ filter: {} }),
        { enabled: true },
      );
      expect(onOpen).toHaveBeenCalledTimes(1);
      fireEvent.click(screen.getByText("Close"));
      expect(useGetList).toHaveBeenLastCalledWith(
        "WebMapServiceOperation",
        expect.anything(),
        { enabled: false },
      );
      expect(onClose).toHaveBeenCalledTimes(1);
    },
  );
  it("preserves searching with a closed dropdown", () => {
    render(
      <SchemaAutocompleteInput
        reference="WebMapServiceOperation"
        source="operations"
      />,
    );
    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "Map" },
    });
    expect(useGetList).toHaveBeenLastCalledWith(
      "WebMapServiceOperation",
      expect.objectContaining({ filter: { search: "Map" } }),
      { enabled: true },
    );
  });
  it.each([true, false])(
    "shows search results once with multiple=%s",
    (multiple) => {
      render(
        <SchemaAutocompleteInput
          reference="WebMapServiceOperation"
          source="operations"
          multiple={multiple ? true : undefined}
        />,
      );
      expect(screen.getAllByRole("option")).toHaveLength(2);
      expect(screen.getAllByRole("option", { name: "GetMap" })).toHaveLength(1);
    },
  );
  it("deduplicates selected and searched records by ID and keeps selected records outside the search", () => {
    state.value = [
      { id: 20, stringRepresentation: "GetMap" },
      { id: 22, stringRepresentation: "Other" },
    ];
    state.fetched = state.value.filter((value) => value != null);
    state.search[0] = { id: "20", stringRepresentation: "GetMap" };
    render(
      <SchemaAutocompleteInput
        reference="WebMapServiceOperation"
        source="operations"
        multiple
      />,
    );
    expect(screen.getAllByRole("option")).toHaveLength(3);
    expect(screen.getAllByRole("option", { name: "GetMap" })).toHaveLength(1);
    expect(screen.getByRole("option", { name: "Other" })).toBeInTheDocument();
  });
  it("retains an included selection without a getMany response and allows distinct IDs with the same label", () => {
    state.value = { id: 99, stringRepresentation: "GetMap" };
    const { rerender } = render(
      <SchemaAutocompleteInput
        reference="WebMapServiceOperation"
        source="operation"
      />,
    );
    expect(screen.getAllByRole("option", { name: "GetMap" })).toHaveLength(2);
    state.search = [];
    rerender(
      <SchemaAutocompleteInput
        reference="WebMapServiceOperation"
        source="operation"
      />,
    );
    expect(screen.getAllByRole("option")).toHaveLength(1);
    expect(screen.getByRole("option")).toHaveValue("99");
  });
});
