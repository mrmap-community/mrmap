import { FormProvider, useForm, type UseFormReturn } from "react-hook-form";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import TimeExtentsInput from "./TimeExtentsInput";

// the form value and the getMany result are driven per test; the create
// mutation answers immediately so the add flow can be followed end to end
const watched = vi.hoisted(() => ({ value: undefined as unknown }));
const fetched = vi.hoisted(() => ({ value: [] as Record<string, unknown>[] }));
const createMutate = vi.hoisted(() => vi.fn());
const notify = vi.hoisted(() => vi.fn());

vi.mock("react-admin", () => ({
  useCreate: () => [createMutate, { isPending: false }],
  useGetMany: () => ({ data: fetched.value }),
  useNotify: () => notify,
  useTranslate: () => (key: string) => key.split(".").pop(),
}));
// the reused read-only field stack reads the schema layer; the spec only
// needs to see which positions a row shows
vi.mock("../../RecordShow/RecordFields", () => ({
  IncludedRecordFields: ({
    record,
    sources,
  }: {
    record?: Record<string, unknown>;
    sources: string[];
  }) => <div>{sources.map((source) => String(record?.[source] ?? "")).join("~")}</div>,
}));

let methods: UseFormReturn | undefined;

const renderWidget = (defaultValues: Record<string, unknown>) => {
  const Wrapper = () => {
    methods = useForm({ defaultValues });
    return (
      <FormProvider {...methods}>
        <TimeExtentsInput source="timeExtents" label="Temporal extents" />
      </FormProvider>
    );
  };
  render(<Wrapper />);
};

describe("TimeExtentsInput", () => {
  it("lists the attached extents, resolving rows through getMany", () => {
    watched.value = [
      {
        id: "te1",
        beginPosition: "2020-01-01T00:00:00Z",
        endPosition: "2020-06-01T00:00:00Z",
      },
      { id: "te2" },
    ];
    fetched.value = [
      { id: "te2", beginPosition: "2021-01-01T00:00:00Z", endPosition: null },
    ];
    renderWidget({ timeExtents: watched.value });
    expect(
      screen.getByText("2020-01-01T00:00:00Z~2020-06-01T00:00:00Z"),
    ).toBeInTheDocument();
    expect(screen.getByText("2021-01-01T00:00:00Z~")).toBeInTheDocument();
  });

  it("refuses to add a time that begins after its end", () => {
    watched.value = [];
    fetched.value = [];
    renderWidget({ timeExtents: [] });
    fireEvent.change(screen.getByLabelText("begin"), {
      target: { value: "2022-01-01T10:00" },
    });
    fireEvent.change(screen.getByLabelText("end"), {
      target: { value: "2021-01-01T10:00" },
    });
    expect(screen.getByText("orderError")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "add" })).toBeDisabled();
  });

  it("creates the row and attaches it as a reference", () => {
    watched.value = [];
    fetched.value = [];
    createMutate.mockImplementation((_resource, _params, options) =>
      options.onSuccess({ data: { id: "te-new" } }),
    );
    renderWidget({ timeExtents: [] });
    fireEvent.change(screen.getByLabelText("begin"), {
      target: { value: "2020-01-01T10:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "add" }));
    expect(createMutate).toHaveBeenCalledWith(
      "TimeExtent",
      { data: { beginPosition: "2020-01-01T10:00:00Z" } },
      expect.anything(),
    );
    expect(methods?.getValues("timeExtents")).toEqual([{ id: "te-new" }]);
    expect(screen.getByLabelText("begin")).toHaveValue("");
    expect(notify).toHaveBeenCalledWith(
      "metadataEditor.timeExtents.added",
      expect.objectContaining({ type: "success" }),
    );
  });

  it("removing detaches the row without touching the record list", () => {
    watched.value = [
      { id: "te1", beginPosition: "a", endPosition: "b" },
      { id: "te2", beginPosition: "c", endPosition: "d" },
    ];
    fetched.value = [];
    renderWidget({ timeExtents: watched.value });
    fireEvent.click(screen.getAllByLabelText("remove")[1]);
    expect(methods?.getValues("timeExtents")).toEqual([{ id: "te1" }]);
  });
});
