import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ScheduleAttentionCounts from "./ScheduleAttentionCounts";

vi.mock("react-admin", () => ({
  Link: ({ to }: { to: string }) => <a href={to}>link</a>,
  useCreatePath: () => ({ resource }: { resource: string }) => `/${resource}`,
  useTranslate: () => (key: string) => key.split(".").pop(),
}));

const alerts = vi.hoisted(() => vi.fn());

vi.mock("../ServiceAlert/useServiceAlerts", () => ({
  default: (filter: Record<string, string>) => alerts(filter),
}));

const answered = (total: number) => ({ total, error: undefined, isPending: false });

describe("ScheduleAttentionCounts", () => {
  it("names nothing while the alerts are not answered", () => {
    alerts.mockReturnValue({ total: 0, error: undefined, isPending: true });
    const { container } = render(<ScheduleAttentionCounts />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names nothing when nobody has a count", () => {
    alerts.mockReturnValue(answered(0));
    const { container } = render(<ScheduleAttentionCounts />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the overdue schedules and leads to their alerts", () => {
    alerts.mockImplementation((filter: Record<string, string>) =>
      answered(filter.category === "harvest_overdue" ? 2 : 0),
    );
    render(<ScheduleAttentionCounts />);
    expect(screen.getByText("attentionTitle")).toBeInTheDocument();
    expect(screen.getByText("harvest_overdue 2")).toBeInTheDocument();
    expect(screen.queryByText(/too_tight/)).not.toBeInTheDocument();
    expect(screen.getByText("link")).toHaveAttribute("href", "/ServiceAlert");
  });
});
