import type { ReactNode } from "react";
import type { RaRecord } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HarvestingJobTabbedShowLayout from "./HarvestingJobTabbedShowLayout";

const state = vi.hoisted(() => ({
  record: { id: 1 } as RaRecord | undefined,
  isPending: false,
  error: null as Error | null,
  // the verdict of the nested log route on the caller: pending until it
  // answered, and a 403 means the log tab must be absent
  logProbe: {
    isPending: false,
    error: null as unknown,
  },
}));
vi.mock("react-admin", () => {
  const Container = ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  );
  return {
    useShowContext: () => state,
    useTranslate: () => (key: string) => key,
    useCreatePath: () => () => "/HarvestingJob/1/show",
    useGetList: () => state.logProbe,
    Link: ({
      to,
      children,
    }: {
      to: string;
      children?: ReactNode;
    }) => <a href={to}>{children}</a>,
    Loading: () => <span>Loading run</span>,
    TabbedShowLayout: Object.assign(Container, {
      Tab: ({ label, children }: { label?: string; children?: ReactNode }) => (
        <div>
          {label}
          {children}
        </div>
      ),
    }),
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
    // source together with the rendered number (#1071) - a render which
    // answers an element renders it, which is how the count links arrive (#1083)
    FunctionField: ({
      source,
      render: renderField,
    }: {
      source: string;
      render: (record: RaRecord) => ReactNode;
    }) => {
      const result = renderField(state.record ?? ({} as RaRecord));
      return typeof result === "object" && result !== null && "props" in result ? (
        <span data-source={source}>{result}</span>
      ) : (
        <span>{`${source}: ${String(result)}`}</span>
      );
    },
    TextField: () => null,
  };
});
vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: () => <span>Related records</span>,
}));
vi.mock("../../../jsonapi/components/ReferenceField", () => ({
  default: () => null,
}));
vi.mock("../HarvestingLog/ListHarvestingLog", () => ({
  default: () => <span>Run log</span>,
}));
vi.mock("./HarvestingRunMissingRecords", () => ({
  default: () => <span>Missing records</span>,
}));
vi.mock("./HarvestingRunSummary", () => ({
  default: ({ logTabAllowed }: { logTabAllowed?: boolean }) => (
    <span>{`Run summary logAllowed=${String(logTabAllowed)}`}</span>
  ),
}));
vi.mock("./HarvestingJobTimingCharts", () => ({
  default: () => <span>Timing chart</span>,
}));
beforeEach(() => {
  state.record = { id: 1 };
  state.isPending = false;
  state.error = null;
  state.logProbe = { isPending: false, error: null };
});
describe("harvesting run detail layout", () => {
  it("renders a successfully loaded run rather than the error banner", () => {
    render(<HarvestingJobTabbedShowLayout />);
    expect(
      screen.getByText("Run summary logAllowed=true"),
    ).toBeInTheDocument();
    expect(screen.getByText("harvestRun.configuration")).toBeInTheDocument();
    expect(screen.getAllByText("Timing chart")).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("names the records the run could not store in a tab of their own", () => {
    // the question the summary cards ask is answered by the tab, not by a
    // guessed table of files (#1083)
    render(<HarvestingJobTabbedShowLayout />);
    expect(
      screen.getByText("harvestRun.failedRecords"),
    ).toBeInTheDocument();
    expect(screen.getByText("Missing records")).toBeInTheDocument();
    expect(screen.queryByText("TemporaryMdMetadataFile")).not.toBeInTheDocument();
  });
  it("links the counts of what the run left behind into that tab", () => {
    state.record = { id: 1, unhandledRecordsCount: 7, importErrorCount: 3 };
    render(<HarvestingJobTabbedShowLayout />);
    const links = screen
      .getAllByRole("link")
      .map((link) => link.getAttribute("href"));
    expect(links).toEqual(
      expect.arrayContaining([
        "/HarvestingJob/1/show/failed-records",
        "/HarvestingJob/1/show/failed-records",
      ]),
    );
    expect(links).toHaveLength(2);
  });
  it("answers nothing for a count the run does not have", () => {
    state.record = { id: 1, unhandledRecordsCount: null, importErrorCount: null };
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
  it("shows the log tab while the caller may read the lines", () => {
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByText("harvestRun.logs")).toBeInTheDocument();
    expect(screen.getByText("Run log")).toBeInTheDocument();
  });
  it("keeps the log tab absent while its verdict is still open", () => {
    state.logProbe = { isPending: true, error: null };
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.queryByText("harvestRun.logs")).not.toBeInTheDocument();
    expect(screen.getByText("harvestRun.failedRecords")).toBeInTheDocument();
  });
  it("keeps the log tab absent when the api denies the lines", () => {
    // the counts are answered by the run and stay shown; only the tab which
    // would list the lines is gone (#1083)
    state.logProbe = { isPending: false, error: { status: 403 } };
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.queryByText("harvestRun.logs")).not.toBeInTheDocument();
    expect(screen.queryByText("Run log")).not.toBeInTheDocument();
    expect(
      screen.getByText("Run summary logAllowed=false"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("harvestRun.failedRecords"),
    ).toBeInTheDocument();
  });
  it("still offers the log tab for a failure which is no denial", () => {
    state.logProbe = { isPending: false, error: { status: 500 } };
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByText("harvestRun.logs")).toBeInTheDocument();
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
    expect(
      screen.queryByText("Run summary logAllowed=false"),
    ).not.toBeInTheDocument();
  });
});
