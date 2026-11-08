import type { AnchorHTMLAttributes } from "react";
import type { RaRecord } from "react-admin";

import { render, screen } from "@testing-library/react";
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
    elapsedSeconds: 180,
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
    // the cards lead to the tabs of the run screen which name those records;
    // the guessed tables are gone and with them the raw resource urls (#1083)
    expect(links).toContain("/HarvestingJob/1/show/DatasetMetadataRecord");
    expect(links).toContain("/HarvestingJob/1/show/ServiceMetadataRecord");
    expect(links).toContain("/HarvestingJob/1/show/failed-records");
    expect(links).toContain("/HarvestingJob/1/show/log");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "harvestingActivity.importErrors",
    );
  });
  it("still shows the counts when the log lines are denied, without the way to them", () => {
    state.run.importStalledAt = "2026-10-08T12:00:00Z";
    render(<HarvestingRunSummary logTabAllowed={false} />);
    const links = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(links).not.toContain("/HarvestingJob/1/show/log");
    expect(links).toContain("/HarvestingJob/1/show/failed-records");
    expect(
      screen.queryByText("harvestRun.viewLogs"),
    ).not.toBeInTheDocument();
  });
  it("leads the records awaiting import to the tab which names them", () => {
    render(<HarvestingRunSummary />);
    const awaiting = screen.getByText("harvestingActivity.awaitingImport");
    expect(awaiting.closest("a")).toHaveAttribute(
      "href",
      "/HarvestingJob/1/show/failed-records",
    );
  });
  it("says on the run when the watchdog sees the import backlog untouched", () => {
    state.run = {
      ...state.run,
      importStalledAt: "2026-10-08T12:00:00Z",
      importErrorCount: 0,
    };
    render(<HarvestingRunSummary />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("harvestRun.importStalled");
    expect(alert).toHaveTextContent("2026-10-08T12:00:00Z");
  });
  it("answers nothing about a stall the watchdog did not report", () => {
    render(<HarvestingRunSummary />);
    expect(
      screen.queryByText("harvestRun.importStalled"),
    ).not.toBeInTheDocument();
  });
  it("shows the elapsed time the api measured, not the browser clock", () => {
    state.run.elapsedSeconds = 61;
    render(<HarvestingRunSummary />);
    expect(screen.getByText("0h 1m 1s")).toBeInTheDocument();
  });
  it("shows an elapsed time although the harvesting never wrote a creation date", () => {
    // the run reads its own creation from its change log, which is what the
    // summary card shows instead of the browser deriving it from a column
    // that is never set (#1071)
    state.run.dateCreated = null;
    state.run.elapsedSeconds = 61;
    render(<HarvestingRunSummary />);
    expect(screen.getByText("0h 1m 1s")).toBeInTheDocument();
    expect(screen.getAllByText("harvestRun.notRecorded")).toHaveLength(1);
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
    state.run.elapsedSeconds = null;
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
