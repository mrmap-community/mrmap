import type { ReactNode } from "react";
import { useRecordContext, useResourceContext } from "react-admin";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ScheduleWarningsField from "./ScheduleWarningsField";

vi.mock("react-admin", () => ({
  Link: ({ to, children }: { to: string; children?: ReactNode }) => (
    <a href={to}>{children}</a>
  ),
  // the field of RelativeDateField reads its moment from the record it is given
  useFieldValue: ({ source, record }: { source: string; record?: unknown }) =>
    (record as Record<string, unknown> | undefined)?.[source],
  useCreatePath: () =>
    ({ resource, id, type }: { resource: string; id: string; type: string }) =>
      `/${resource}/${id}/${type}`,
  useRecordContext: vi.fn(),
  useResourceContext: vi.fn(() => "PeriodicHarvestingJob"),
  // the last segment names the message; interpolation parameters are appended
  // so the spec can see which evidence reached the text
  useTranslate: () => (key: string, options?: Record<string, unknown>) =>
    options?.value != null
      ? `${key.split(".").pop()}=${options.value}`
      : key.split(".").pop(),
}));

const HOUR = 60 * 60 * 1000;

const ago = (ms: number) => new Date(Date.now() - ms).toISOString();

const overdue = {
  code: "schedule_overdue",
  severity: "warning",
  interval: "P1D",
  lastDoneAt: ago(30 * HOUR),
  expectedAt: ago(6 * HOUR),
  computedAt: ago(6 * HOUR),
};

const tooTight = {
  code: "schedule_too_tight",
  severity: "warning",
  interval: "PT26H",
  observedDuration: "PT27H",
  sampleCount: 5,
};

const insufficient = {
  code: "insufficient_evidence",
  severity: "info",
  interval: "P1D",
  sampleCount: 1,
  unknownReason: "too_few_samples",
};

const renderRow = (record: Record<string, unknown>) => {
  vi.mocked(useRecordContext).mockReturnValue(record);
  return render(<ScheduleWarningsField />);
};

describe("ScheduleWarningsField", () => {
  it("answers nothing for a row which needs no attention", () => {
    const { container, unmount } = renderRow({ id: "1" });
    expect(container).toBeEmptyDOMElement();
    unmount();
    renderRow({ id: "1", scheduleWarnings: [] });
    expect(container).toBeEmptyDOMElement();
    unmount();
    renderRow({ id: "1", scheduleWarnings: null });
    expect(container).toBeEmptyDOMElement();
  });

  it("names the first warning with its label and nothing else", () => {
    renderRow({ id: "1", scheduleWarnings: [overdue] });
    expect(screen.getByText("schedule_overdue")).toBeInTheDocument();
    // one warning needs no counter
    expect(screen.queryByText(/\(\+\d\)/)).not.toBeInTheDocument();
  });

  it("counts the warnings which the label of the first one stands for", () => {
    renderRow({ id: "1", scheduleWarnings: [overdue, tooTight] });
    expect(screen.getByText(/schedule_overdue \(\+1\)/)).toBeInTheDocument();
  });

  it("opens the evidence of every warning on click", () => {
    renderRow({ id: "1", scheduleWarnings: [tooTight, insufficient, overdue] });
    // the cell names the first warning with a counter behind it
    fireEvent.click(screen.getByText(/schedule_too_tight/));

    expect(screen.getByText("interval=PT26H")).toBeInTheDocument();
    expect(screen.getByText("observed=PT27H")).toBeInTheDocument();
    expect(screen.getAllByText("samples")).toHaveLength(2);
    expect(screen.getByText("too_few_samples")).toBeInTheDocument();
    // the moments of the rows are read relatively, not by their absolute value
    expect(screen.getAllByText(/ago/).length).toBeGreaterThan(0);
  });

  it("leads from the details to the edit of the setting itself", () => {
    renderRow({ id: "1", scheduleWarnings: [overdue] });
    fireEvent.click(screen.getByText("schedule_overdue"));

    const action = screen.getByText("checkSchedule").closest("a");
    expect(action).toHaveAttribute(
      "href",
      "/PeriodicHarvestingJob/1/edit",
    );
  });

  it("reads the record it is given beside the record of the screen", () => {
    vi.mocked(useRecordContext).mockReturnValue(undefined);
    render(
      <ScheduleWarningsField record={{ id: "42", scheduleWarnings: [overdue] }} />,
    );
    fireEvent.click(screen.getByText("schedule_overdue"));
    expect(screen.getByText("checkSchedule").closest("a")).toHaveAttribute(
      "href",
      "/PeriodicHarvestingJob/42/edit",
    );
  });

  it("answers no action when the row names no resource to edit", () => {
    vi.mocked(useResourceContext).mockReturnValue(undefined);
    renderRow({ id: "1", scheduleWarnings: [overdue] });
    fireEvent.click(screen.getByText("schedule_overdue"));
    expect(screen.queryByText("checkSchedule")).not.toBeInTheDocument();
  });
});
