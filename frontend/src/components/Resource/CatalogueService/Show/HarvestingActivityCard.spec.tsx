import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RaRecord } from "react-admin";
import type { ReactNode } from "react";
import HarvestingActivityCard, {
  HarvestingActivityList,
  HarvestingPhaseStepper,
} from "./HarvestingActivityCard";
import ListGuesser from "../../../../jsonapi/components/ListGuesser";

const state = vi.hoisted(() => ({
  data: [] as RaRecord[],
  isPending: false,
  error: null as Error | null,
}));
vi.mock("react-admin", () => ({
  useListContext: () => state,
  useRecordContext: () => ({ id: "csw-1" }),
  useTranslate: () => (key: string, options?: Record<string, unknown>) =>
    options?.count === undefined ? key : `${key}: ${options.count}`,
  RecordContextProvider: ({ children }: { children: ReactNode }) => children,
  Button: ({ to, label }: { to: string; label: string }) => (
    <a href={to}>{label}</a>
  ),
  DateField: () => <span>Started</span>,
  NumberField: () => null,
  Loading: () => <span>Loading</span>,
}));
vi.mock("../../../../jsonapi/components/ListGuesser", () => ({
  default: vi.fn(() => null),
}));
vi.mock("../../../../jsonapi/hooks/useOperation", () => ({
  default: () => ({}),
}));
vi.mock("../HarvestingDailyStatsChart", () => ({ default: () => null }));
beforeEach(() => {
  state.data = [];
  state.isPending = false;
  state.error = null;
});
describe("harvesting activity", () => {
  it("requests current processing fields independently of saved table preferences", () => {
    render(<HarvestingActivityCard />);
    const props = vi.mocked(ListGuesser).mock.calls.at(-1)?.[0];
    expect(props?.sort).toEqual({ field: "dateCreated", order: "DESC" });
    expect(props?.refetchInterval).toBe(5000);
    expect(props?.queryOptions?.meta).toMatchObject({
      jsonApiParams: {
        "fields[HarvestingJob]": expect.stringContaining("phase_label"),
      },
    });
    expect(props?.queryOptions?.meta).toMatchObject({
      jsonApiParams: {
        "fields[HarvestingJob]": expect.stringContaining(
          "unhandled_records_count",
        ),
      },
    });
  });
  it("shows active stage and discovery without a misleading zero percent", () => {
    state.data = [
      {
        id: "run-1",
        phaseLabel: "get total records count",
        doneAt: null,
        totalRecords: null,
        progress: 0,
      },
    ];
    render(<HarvestingActivityList />);
    expect(
      screen.getByText("harvestingActivity.processing"),
    ).toBeInTheDocument();
    expect(screen.getByText("get total records count")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).not.toHaveAttribute(
      "aria-valuenow",
    );
    expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
  });
  it("shows progress, outstanding records, errors, and run details", () => {
    state.data = [
      {
        id: "run-2",
        phaseLabel: "records to db",
        doneAt: null,
        totalRecords: 200,
        unhandledRecordsCount: 60,
        importErrorCount: 2,
        progress: 70,
      },
    ];
    render(<HarvestingActivityList />);
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "70",
    );
    expect(
      screen.getByText("harvestingActivity.totalRecords: 200"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("harvestingActivity.awaitingImport: 60"),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "harvestingActivity.importErrors: 2",
    );
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "/HarvestingJob/run-2/show",
    );
  });
  it("keeps cancelled outcomes visible rather than claiming success", () => {
    state.data = [
      {
        id: "run-3",
        phaseLabel: "aborted",
        doneAt: "2026-10-08T10:00:00Z",
        totalRecords: 200,
        progress: 40,
      },
    ];
    render(<HarvestingActivityList />);
    expect(screen.getByText("aborted")).toBeInTheDocument();
    expect(screen.getByText("harvestingActivity.finished")).toBeInTheDocument();
    expect(
      screen.queryByText("harvestingActivity.processing"),
    ).not.toBeInTheDocument();
  });
  it("distinguishes empty, loading, and error states", () => {
    const { rerender } = render(<HarvestingActivityList />);
    expect(screen.getByText("harvestingActivity.empty")).toBeInTheDocument();
    state.isPending = true;
    rerender(<HarvestingActivityList />);
    expect(screen.getByText("Loading")).toBeInTheDocument();
    state.isPending = false;
    state.error = new Error("Offline");
    rerender(<HarvestingActivityList />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "harvestingActivity.loadError",
    );
  });
});

describe("harvesting workflow stages", () => {
  it.each([
    [0, "waiting", "waiting", "waiting"],
    [1, "inProgress", "waiting", "waiting"],
    [2, "completed", "inProgress", "waiting"],
    [3, "completed", "completed", "inProgress"],
    [4, "completed", "completed", "completed"],
    [5, "unknown", "unknown", "unknown"],
    [4711, "unknown", "unknown", "unknown"],
  ])(
    "shows the correct stage states for phase %s",
    (phase, discover, download, importing) => {
      render(<HarvestingPhaseStepper phase={Number(phase)} />);
      for (const [stage, status] of [
        ["discover", discover],
        ["download", download],
        ["import", importing],
      ]) {
        expect(
          screen.getByLabelText(
            `harvestingActivity.stages.${stage}: harvestingActivity.stageStatus.${status}`,
          ),
        ).toBeInTheDocument();
      }
    },
  );
  it("labels the recorded start time", () => {
    state.data = [
      {
        id: "run-1",
        phase: 2,
        phaseLabel: "download records",
        dateCreated: "2026-10-08T10:00:00Z",
        doneAt: null,
      },
    ];
    render(<HarvestingActivityList />);
    expect(screen.getByText(/harvestingActivity.started/)).toBeInTheDocument();
    expect(screen.getByText("Started")).toBeInTheDocument();
  });
});
