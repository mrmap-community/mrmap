import { act, render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import type { RaRecord } from "react-admin";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HarvestingRunSummary from "./HarvestingRunSummary";

const state = vi.hoisted(() => ({ run: { id: 1 } as RaRecord }));
vi.mock("react-admin", () => ({
  useRecordContext: () => state.run,
  useTranslate: () => (key: string, options?: Record<string, unknown>) =>
    options?.id ? `${key} ${options.id}` : key,
  useCreatePath: () => () => "/HarvestingJob/1/show",
  DateField: ({ source, emptyText }: { source: string; emptyText: string }) => (
    <span>{state.run[source] ?? emptyText}</span>
  ),
  Link: ({
    to,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) => (
    <a href={to} {...props} />
  ),
}));
vi.mock("../../../jsonapi/components/ReferenceField", () => ({
  default: () => <a href="/CatalogueService/csw-1/show">Catalogue</a>,
}));
vi.mock("../../../jsonapi/components/Count", () => ({
  Count: ({
    resource,
    refetchInterval,
  }: {
    resource: string;
    refetchInterval: number | false;
  }) => (
    <span data-testid={resource} data-refresh={String(refetchInterval)}>
      12
    </span>
  ),
}));
vi.mock("./HarvestingJobActions", () => ({
  default: () => <span>Run actions</span>,
}));
vi.mock("./HarvestingPhaseStepper", () => ({
  default: ({ phase }: { phase: number }) => <span>Stepper {phase}</span>,
}));
beforeEach(() => {
  state.run = {
    id: 1,
    phase: 3,
    phaseLabel: "Importing records",
    totalRecords: 100,
    unhandledRecordsCount: 40,
    importErrorCount: 2,
    progress: 60,
    dateCreated: "2026-10-08T10:00:00Z",
    doneAt: null,
  };
});
afterEach(() => vi.useRealTimers());
describe("harvesting run summary", () => {
  it("shows phase, progress, linked counters and import errors", () => {
    render(<HarvestingRunSummary />);
    expect(screen.getByText("Stepper 3")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "60",
    );
    expect(screen.getByTestId("DatasetMetadataRecord")).toHaveAttribute(
      "data-refresh",
      "5000",
    );
    const links = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(links).toContain("/HarvestingJob/1/show/DatasetMetadataRecord");
    expect(links).toContain("/HarvestingJob/1/show/ServiceMetadataRecord");
    expect(links).toContain("/HarvestingJob/1/show/TemporaryMdMetadataFile");
    expect(links).toContain("/HarvestingJob/1/show/HarvestingLog");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "harvestingActivity.importErrors",
    );
  });
  it("updates elapsed time for active runs", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-08T10:01:00Z"));
    render(<HarvestingRunSummary />);
    expect(screen.getByText("0h 1m 0s")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByText("0h 1m 2s")).toBeInTheDocument();
  });
  it("freezes elapsed time and counter polling when a run ends", () => {
    state.run.doneAt = "2026-10-08T10:03:00Z";
    render(<HarvestingRunSummary />);
    expect(screen.getByText("0h 3m 0s")).toBeInTheDocument();
    expect(screen.getByTestId("DatasetMetadataRecord")).toHaveAttribute(
      "data-refresh",
      "false",
    );
  });
  it("does not invent a missing start time or duration", () => {
    state.run.dateCreated = null;
    render(<HarvestingRunSummary />);
    expect(screen.getAllByText("harvestRun.notRecorded")).toHaveLength(2);
  });
  it("shows indeterminate progress while discovering the total", () => {
    state.run.totalRecords = null;
    render(<HarvestingRunSummary />);
    expect(screen.getByRole("progressbar")).not.toHaveAttribute(
      "aria-valuenow",
    );
    expect(
      screen.getByText("harvestingActivity.discovering"),
    ).toBeInTheDocument();
  });
});
