import type { ReactNode } from "react";
import type { RaRecord } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ListGuesser from "../../../jsonapi/components/ListGuesser";
import ListTemporaryMdMetadataFile from "../TemporaryMdMetadataFile/ListTemporaryMdMetadataFile";
import HarvestingRunMissingRecords, {
  HarvestedRecordReferenceField,
} from "./HarvestingRunMissingRecords";

const state = vi.hoisted(() => ({
  record: { id: 1 } as RaRecord | undefined,
}));

vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: vi.fn(() => null),
}));
vi.mock("../../../jsonapi/components/ReferenceField", () => ({
  default: ({
    source,
    reference,
    label,
  }: {
    source: string;
    reference: string;
    label?: string;
  }) => <span>{`${source}:${reference}:${label}`}</span>,
}));
vi.mock("../../Lists/CustomListActions", () => ({
  default: () => null,
}));
vi.mock("../TemporaryMdMetadataFile/ListTemporaryMdMetadataFile", () => ({
  default: vi.fn(() => <span>Refused files</span>),
}));
vi.mock("react-admin", () => ({
  useRecordContext: () => state.record,
  useTranslate: () => (key: string) => key,
  DateField: () => null,
  FunctionField: () => null,
}));

beforeEach(() => {
  state.record = { id: 1 };
  vi.mocked(ListTemporaryMdMetadataFile).mockClear();
  vi.mocked(ListGuesser).mockClear();
});

describe("HarvestingRunMissingRecords", () => {
  it("shows both answers the run gives about what it did not store", () => {
    render(<HarvestingRunMissingRecords />);
    expect(
      screen.getByText("harvestRun.refusedByImport"),
    ).toBeInTheDocument();
    expect(screen.getByText("harvestRun.collectedStates")).toBeInTheDocument();
    expect(screen.getByText("Refused files")).toBeInTheDocument();
    const refusedProps = vi
      .mocked(ListTemporaryMdMetadataFile)
      .mock.calls.at(-1)?.[0];
    expect(refusedProps?.relatedResource).toEqual({
      resource: "HarvestingJob",
      id: 1,
    });
    const relationProps = vi.mocked(ListGuesser).mock.calls.at(-1)?.[0];
    expect(relationProps?.resource).toBe("HarvestedMetadataRelation");
    expect(relationProps?.relatedResource).toEqual({
      resource: "HarvestingJob",
      id: 1,
    });
    expect(relationProps?.sort).toEqual({
      field: "historyDate",
      order: "DESC",
    });
  });
  it("keeps both lists fresh while the run is still going", () => {
    state.record = { id: 1, doneAt: "2026-11-01T10:00:00Z" };
    render(<HarvestingRunMissingRecords />);
    expect(
      vi.mocked(ListTemporaryMdMetadataFile).mock.calls.at(-1)?.[0]
        .refetchInterval,
    ).toBe(false);
    expect(vi.mocked(ListGuesser).mock.calls.at(-1)?.[0].refetchInterval).toBe(
      false,
    );
  });
  it("answers nothing without a run to ask about", () => {
    state.record = undefined;
    const { container } = render(<HarvestingRunMissingRecords />);
    expect(container).toBeEmptyDOMElement();
  });
  it("words the collecting state of a relation row", () => {
    render(<HarvestingRunMissingRecords />);
    const columns =
      vi.mocked(ListGuesser).mock.calls.at(-1)?.[0].columns ?? [];
    const stateColumn = columns.find(
      (column) => column.key === "collectingState",
    );
    const renderState = (
      stateColumn?.props as unknown as {
        render: (record: RaRecord) => ReactNode;
      }
    ).render;
    render(<>{renderState({ id: 1, collectingState: 0 })}</>);
    expect(
      screen.getByText("harvestRun.collectingStates.duplicated"),
    ).toBeInTheDocument();
    render(<>{renderState({ id: 1, collectingState: 4 })}</>);
    expect(
      screen.getByText("harvestRun.collectingStates.removed"),
    ).toBeInTheDocument();
  });
  it("links a relation row to the record it made, whichever kind it was", () => {
    state.record = {
      id: 1,
      collectingState: 1,
      serviceMetadataRecord: { id: "42" },
    };
    render(<HarvestedRecordReferenceField />);
    expect(
      screen.getByText(
        "serviceMetadataRecord:ServiceMetadataRecord:harvestRun.collectedRecord",
      ),
    ).toBeInTheDocument();
  });
  it("reads the record column of a row without a record as empty", () => {
    state.record = { id: 1, collectingState: 4 };
    render(<HarvestedRecordReferenceField />);
    // falls back to a source which is unset, which answers its empty text
    expect(
      screen.getByText(
        "datasetMetadataRecord:DatasetMetadataRecord:harvestRun.collectedRecord",
      ),
    ).toBeInTheDocument();
  });
});
