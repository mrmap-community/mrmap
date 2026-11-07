import type { ReactNode } from "react";
import type { RaRecord } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HarvestingJobTabbedShowLayout from "./HarvestingJobTabbedShowLayout";

const state = vi.hoisted(() => ({
  record: { id: 1 } as RaRecord | undefined,
  isPending: false,
  error: null as Error | null,
}));
vi.mock("react-admin", () => {
  const Container = ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  );
  return {
    useShowContext: () => state,
    useTranslate: () => (key: string) => key,
    Loading: () => <span>Loading run</span>,
    TabbedShowLayout: Object.assign(Container, { Tab: Container }),
    SimpleShowLayout: Container,
    Labeled: Container,
    BooleanField: () => null,
    DateField: ({
      source,
      emptyText,
    }: {
      source: string;
      emptyText?: string;
    }) => (
      <span>
        {source}: {state.record?.[source] ?? emptyText}
      </span>
    ),
    NumberField: () => null,
    // the measurements of a run are derived values, so the field answers its
    // source together with the rendered number (#1071)
    FunctionField: ({
      source,
      render,
    }: {
      source: string;
      render: (record: RaRecord) => unknown;
    }) => <span>{`${source}: ${String(render(state.record ?? ({} as RaRecord)))}`}</span>,
    TextField: () => null,
  };
});
vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: () => <span>Related records</span>,
}));
vi.mock("../../../jsonapi/components/ReferenceField", () => ({
  default: () => null,
}));
vi.mock("./HarvestingRunSummary", () => ({
  default: () => <span>Run summary</span>,
}));
vi.mock("./HarvestingJobTimingCharts", () => ({
  default: () => <span>Timing chart</span>,
}));
beforeEach(() => {
  state.record = { id: 1 };
  state.isPending = false;
  state.error = null;
});
describe("harvesting run detail layout", () => {
  it("renders a successfully loaded run rather than the error banner", () => {
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByText("Run summary")).toBeInTheDocument();
    expect(screen.getByText("harvestRun.configuration")).toBeInTheDocument();
    expect(screen.getAllByText("Timing chart")).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("shows the measurements this run answers about its own work", () => {
    state.record = {
      id: 1,
      elapsedSeconds: 61,
      fetchRecordDuration: "0:10:00.000000",
      mdMetadataFileToDbDuration: "0:05:00.000000",
      recordsPerMinuteRunning: 48.6,
      estimatedSecondsRemaining: 120,
      expectedDoneAt: "2026-10-08T11:00:00Z",
    };
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByText("elapsedSeconds: 0h 1m 1s")).toBeInTheDocument();
    expect(
      screen.getByText("fetchRecordDuration: 0h 10m 0s"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("mdMetadataFileToDbDuration: 0h 5m 0s"),
    ).toBeInTheDocument();
    expect(screen.getByText("recordsPerMinuteRunning: 49")).toBeInTheDocument();
    expect(
      screen.getByText("estimatedSecondsRemaining: 0h 2m 0s"),
    ).toBeInTheDocument();
    expect(screen.getByText("harvestRun.estimateNote")).toBeInTheDocument();
  });
  it("words the missing estimate as unknown and never as a duration", () => {
    // a run which does not know its records yet, and a closed run, both have
    // nothing to estimate - an invented number must not look measured (#1071)
    state.record = { id: 1, estimatedSecondsRemaining: null };
    render(<HarvestingJobTabbedShowLayout />);
    expect(
      screen.getByText(
        "estimatedSecondsRemaining: harvestRun.estimateUnknown",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("expectedDoneAt: harvestRun.estimateUnknown"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("recordsPerMinuteRunning: harvestRun.notRecorded"),
    ).toBeInTheDocument();
  });
  it("shows loading while the request is pending", () => {
    state.isPending = true;
    state.record = undefined;
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByText("Loading run")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("waits for a record when one is not yet available", () => {
    state.record = undefined;
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByText("Loading run")).toBeInTheDocument();
  });
  it("shows an error only when the request fails", () => {
    state.record = undefined;
    state.error = new Error("Unavailable");
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "harvestingActivity.loadError",
    );
    expect(screen.queryByText("Run summary")).not.toBeInTheDocument();
  });
});
