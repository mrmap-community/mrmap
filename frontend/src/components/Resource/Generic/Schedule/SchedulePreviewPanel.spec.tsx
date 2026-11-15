import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SchedulePreviewPanel, {
  type SchedulePreviewAnswer,
  type ScheduleSuggestion,
} from "./SchedulePreviewPanel";

const { MockHttpError } = vi.hoisted(() => {
  class MockHttpError extends Error {
    body: unknown;
    status: number;
    constructor(message: string, status: number, body?: unknown) {
      super(message);
      this.status = status;
      this.body = body;
    }
  }
  return { MockHttpError };
});

const state = vi.hoisted(() => ({
  custom: vi.fn(),
  record: undefined as { id: string | number } | undefined,
  values: {} as Record<string, unknown>,
  setValue: vi.fn(),
}));

vi.mock("react-admin", () => ({
  HttpError: MockHttpError,
  useTranslate:
    () =>
    (key: string, args?: { detail?: string }) =>
      args?.detail !== undefined
        ? `${key.split(".").pop()}:${args.detail}`
        : key.split(".").pop(),
  useDataProvider: () => ({ custom: state.custom }),
  useRecordContext: () => state.record,
}));

vi.mock("react-hook-form", () => ({
  useWatch: () => state.values,
  useFormContext: () => ({ setValue: state.setValue }),
}));

const answer = (
  overrides: Partial<SchedulePreviewAnswer> = {},
): SchedulePreviewAnswer => ({
  id: "preview-1",
  operation: "monitoring",
  serviceKind: "WebMapService",
  serviceId: "1",
  settingId: null,
  scheduling: "*/5 * * * * UTC",
  enabled: true,
  nextOccurrences: ["2026-11-15T10:00:00Z"],
  intervalSeconds: 300,
  potentialOverlap: null,
  overlapBasis: null,
  elapsed: {
    evidence: "measured_elapsed",
    p50Seconds: 600,
    p95Seconds: null,
    averageSeconds: null,
    sampleCount: 3,
    p95MinimumSamples: 20,
    failedCount: 0,
    incompleteCount: 0,
    lookbackDays: 180,
    lastMeasurementAt: null,
  },
  warningCodes: ["insufficient_samples"],
  warnings: [
    { code: "insufficient_samples", message: "too few completed runs" },
  ],
  capacity: null,
  capacityReason: "no durable per-task worker events are recorded",
  suggestions: [],
  suggestionsReason: null,
  suggestionsReasonCode: null,
  suggestionsHorizonDays: null,
  settingRevision: null,
  asOf: "2026-11-15T09:00:00Z",
  expiresAt: "2026-11-15T09:02:00Z",
  ...overrides,
});

/** one alternative as the engine of #1328 answers it */
const suggestion = (
  overrides: Partial<ScheduleSuggestion> = {},
): ScheduleSuggestion => ({
  crontab: "7,37 * * * *",
  timezone: "UTC",
  horizonDays: 7,
  horizonStart: "2026-11-16T00:00:00Z",
  horizonEnd: "2026-11-23T00:00:00Z",
  firingCount: 336,
  queue: "monitoring",
  originalWorkerSeconds: 3360,
  expectedWorkerSeconds: 0,
  sampleCount: 25,
  costCoverage: 1,
  snapshotAt: "2026-11-16T00:00:00Z",
  reason: "keeps the 336 firings and expects less occupancy",
  ...overrides,
});

describe("SchedulePreviewPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.record = undefined;
    state.values = {
      service: { id: "42" },
      scheduleInterval: "0 8 * * *",
      enabled: true,
    };
    state.custom.mockResolvedValue({ data: answer() });
  });

  it("asks the preview endpoint with the draft of the form, never the save", async () => {
    render(
      <SchedulePreviewPanel
        operation="monitoring"
        serviceKind="WebMapService"
        serviceId="42"
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(state.custom).toHaveBeenCalledOnce());
    expect(state.custom).toHaveBeenCalledWith("preview_scheduling", {
      method: "POST",
      body: {
        data: {
          type: "SchedulingPreview",
          attributes: {
            operation: "monitoring",
            serviceKind: "WebMapService",
            serviceId: "42",
            enabled: true,
            scheduling: "0 8 * * *",
          },
        },
      },
    });
  });

  it("names the edited setting so the answer is decided against it", async () => {
    state.record = { id: 7 };
    render(
      <SchedulePreviewPanel
        operation="monitoring"
        serviceKind="WebMapService"
        serviceId="42"
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(state.custom).toHaveBeenCalledOnce());
    const body = state.custom.mock.calls[0][1].body as {
      data: { attributes: Record<string, unknown> };
    };
    expect(body.data.attributes.settingId).toBe(7);
  });

  it("reads the service of the form when the injection site has none", async () => {
    state.values = {
      ...state.values,
      scheduling: "*/10 * * * * UTC+2",
    };
    render(<SchedulePreviewPanel operation="harvest" serviceKind="CatalogueService" />);
    fireEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(state.custom).toHaveBeenCalledOnce());
    const body = state.custom.mock.calls[0][1].body as {
      data: { attributes: Record<string, unknown> };
    };
    expect(body.data.attributes.serviceId).toBe("42");
    expect(body.data.attributes.operation).toBe("harvest");
    expect(body.data.attributes.scheduling).toBe("*/10 * * * * UTC+2");
  });

  it("answers with the coming runs, the honest durations and the warnings", async () => {
    render(
      <SchedulePreviewPanel
        operation="monitoring"
        serviceKind="WebMapService"
        serviceId="42"
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(await screen.findByText("5.0 min")).toBeInTheDocument();
    expect(await screen.findByText("10 min")).toBeInTheDocument();
    // a p95 its evidence does not allow stays "unknown", it is not zero
    const p95Row = screen.getByText("p95").parentElement as HTMLElement;
    expect(p95Row).toHaveTextContent("unknown");
    expect(
      await screen.findByText("too few completed runs"),
    ).toBeInTheDocument();
    expect(await screen.findByText("3")).toBeInTheDocument();
  });

  it("marks the answer as stale when the draft moved on", async () => {
    const { rerender } = render(
      <SchedulePreviewPanel
        operation="monitoring"
        serviceKind="WebMapService"
        serviceId="42"
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    await screen.findByText("too few completed runs");
    expect(screen.queryByText("stale")).not.toBeInTheDocument();
    state.values = { ...state.values, scheduleInterval: "0 9 * * *" };
    rerender(
      <SchedulePreviewPanel
        operation="monitoring"
        serviceKind="WebMapService"
        serviceId="42"
      />,
    );
    expect(await screen.findByText("stale")).toBeInTheDocument();
  });

  it("shows the field error of a rejected crontab instead of failing silently", async () => {
    state.custom.mockRejectedValue(
      new MockHttpError("Request failed", 400, {
        errors: {
          scheduling: "Invalid crontab format — expected 5 fields",
        },
      }),
    );
    render(
      <SchedulePreviewPanel
        operation="monitoring"
        serviceKind="WebMapService"
        serviceId="42"
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(
      await screen.findByText(
        "error:Invalid crontab format — expected 5 fields",
      ),
    ).toBeInTheDocument();
  });

  it("answers the alternatives with their evidence and applies none", async () => {
    state.custom.mockResolvedValue({
      data: answer({ suggestions: [suggestion()] }),
    });
    render(
      <SchedulePreviewPanel
        operation="monitoring"
        serviceKind="WebMapService"
        serviceId="42"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /button/i }));
    expect(await screen.findByText("7,37 * * * *")).toBeInTheDocument();
    // the verified cadence and the measured occupancy travel with it
    expect(await screen.findByText("336 / 7 d")).toBeInTheDocument();
    expect(await screen.findByText("0 s / 56 min")).toBeInTheDocument();
    expect(
      await screen.findByText("keeps the 336 firings and expects less occupancy"),
    ).toBeInTheDocument();
    // nothing was applied: only an explicit click writes the form
    expect(state.setValue).not.toHaveBeenCalled();
  });

  it("writes the clicked alternative into the crontab field of the form", async () => {
    state.custom.mockResolvedValue({
      data: answer({ suggestions: [suggestion()] }),
    });
    render(
      <SchedulePreviewPanel
        operation="monitoring"
        serviceKind="WebMapService"
        serviceId="42"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /button/i }));
    fireEvent.click(await screen.findByRole("button", { name: /7,37/ }));
    expect(state.setValue).toHaveBeenCalledWith(
      "scheduleInterval",
      "7,37 * * * *",
      expect.objectContaining({ shouldDirty: true }),
    );
  });

  it("keeps the timezone the harvesting form carries when applying", async () => {
    state.values = { ...state.values, scheduling: "0 12 * * 1-5 UTC+2" };
    state.custom.mockResolvedValue({
      data: answer({
        suggestions: [
          suggestion({ crontab: "5 12 * * 1-5", firingCount: 5 }),
        ],
      }),
    });
    render(<SchedulePreviewPanel operation="harvest" serviceKind="CatalogueService" />);
    fireEvent.click(screen.getByRole("button", { name: /button/i }));
    fireEvent.click(await screen.findByRole("button", { name: /5 12/ }));
    expect(state.setValue).toHaveBeenCalledWith(
      "scheduling",
      "5 12 * * 1-5 UTC+2",
      expect.objectContaining({ shouldDirty: true }),
    );
  });

  it("says why nothing was suggested instead of showing a free minute", async () => {
    state.custom.mockResolvedValue({
      data: answer({
        suggestionsReason:
          "the deployment capacity snapshot answers no verified cost",
        suggestionsReasonCode: "capacity_unverified",
        suggestionsHorizonDays: 7,
      }),
    });
    render(
      <SchedulePreviewPanel
        operation="monitoring"
        serviceKind="WebMapService"
        serviceId="42"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /button/i }));
    expect(
      await screen.findByText(
        "the deployment capacity snapshot answers no verified cost",
      ),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole("button")).toHaveLength(1);
    expect(state.setValue).not.toHaveBeenCalled();
  });

  it("refuses to ask for a schedule it cannot attribute to a service", () => {
    state.values = { ...state.values, service: undefined };
    render(<SchedulePreviewPanel operation="monitoring" />);
    expect(screen.getByRole("button")).toBeDisabled();
    expect(screen.getByText("missingService")).toBeInTheDocument();
  });
});
