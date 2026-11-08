import type { ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ScheduleAttentionCounts from "./ScheduleAttentionCounts";

vi.mock("react-admin", () => ({
  Link: ({ to, children }: { to: string; children?: ReactNode }) => (
    <a href={to}>{children}</a>
  ),
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
    const link = screen.getByText("harvest_overdue 2");
    expect(link).toBeInTheDocument();
    expect(screen.queryByText(/too_tight/)).not.toBeInTheDocument();
    expect(link.closest("a")).toHaveAttribute(
      "href",
      `/ServiceAlert?filter=${encodeURIComponent(
        JSON.stringify({ category: "harvest_overdue", serviceType: "CatalogueService" }),
      )}`,
    );
  });
});
