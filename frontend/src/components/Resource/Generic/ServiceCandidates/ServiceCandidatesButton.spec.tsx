import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ServiceCandidatesButton from "./ServiceCandidatesButton";

const state = vi.hoisted(() => ({
  resource: "DatasetMetadataRecord" as string | undefined,
  record: { id: "record-1" } as { id?: string } | undefined,
  operations: [] as string[],
}));

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
  useResourceContext: () => state.resource,
  useRecordContext: (props?: { record?: { id?: string } }) =>
    props?.record ?? state.record,
}));

vi.mock("../../../../jsonapi/hooks/useOperation", () => ({
  default: (operationId?: string) =>
    operationId && state.operations.includes(operationId) ? {} : undefined,
}));

vi.mock("./ServiceCandidatesDialog", () => ({
  default: ({ recordId }: { recordId: string }) => (
    <div>Dialog of {recordId}</div>
  ),
}));

beforeEach(() => {
  state.resource = "DatasetMetadataRecord";
  state.record = { id: "record-1" };
  state.operations = ["service_candidates_DatasetMetadataRecord"];
});

describe("the candidates action of a record", () => {
  it("offers the action wherever the api answers the resolution", () => {
    render(<ServiceCandidatesButton />);
    expect(screen.getByText("serviceCandidates.button")).toBeInTheDocument();
    // the dialog of the record costs nothing until it is opened
    expect(screen.queryByText("Dialog of record-1")).not.toBeInTheDocument();
  });

  it("stays away from a resource whose candidates the api does not answer", () => {
    state.operations = [];
    render(<ServiceCandidatesButton />);
    expect(
      screen.queryByText("serviceCandidates.button"),
    ).not.toBeInTheDocument();
  });

  it("stays away from a row without a record", () => {
    state.record = undefined;
    render(<ServiceCandidatesButton />);
    expect(
      screen.queryByText("serviceCandidates.button"),
    ).not.toBeInTheDocument();
  });

  it("opens the dialog of the record it belongs to", () => {
    state.resource = "ServiceMetadataRecord";
    state.operations = ["service_candidates_ServiceMetadataRecord"];
    render(<ServiceCandidatesButton />);
    fireEvent.click(screen.getByText("serviceCandidates.button"));
    expect(screen.getByText("Dialog of record-1")).toBeInTheDocument();
  });

  it("asks the record a list row hands over instead of its own", () => {
    render(<ServiceCandidatesButton record={{ id: "row-7" }} />);
    fireEvent.click(screen.getByText("serviceCandidates.button"));
    expect(screen.getByText("Dialog of row-7")).toBeInTheDocument();
  });
});
