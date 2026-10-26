import type { ReactNode } from "react";
import type { SortPayload } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkQueueCard, { workQueues } from "./WorkQueueCard";

const state = vi.hoisted(() => ({
  /** what every queue asked the api for, in the order the card asks it */
  asked: [] as {
    resource: string;
    filter?: Record<string, unknown>;
    sort?: SortPayload;
  }[],
  /** the total the api answered per resource */
  totals: {} as Record<string, number>,
}));

vi.mock("../../../jsonapi/components/Count", () => ({
  Count: ({
    resource,
    filter,
    sort,
  }: {
    resource: string;
    filter?: Record<string, unknown>;
    sort?: SortPayload;
  }) => {
    state.asked.push({ resource, filter, sort });
    return <>{state.totals[resource] ?? 0}</>;
  },
}));

vi.mock("../../Resource/BackgroundProcess/ListBackgroundProcess", () => ({
  // the api answers the statuses of a process as a comma separated list
  ACTIVE_STATUSES: "pending,running",
}));

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
}));

vi.mock("../../MUI/SimpleCard", () => ({
  default: ({
    title,
    children,
  }: {
    title?: ReactNode;
    children?: ReactNode;
  }) => (
    <section>
      <h2>{title}</h2>
      {children}
    </section>
  ),
}));

beforeEach(() => {
  state.asked = [];
  state.totals = { ServiceAlert: 7, BackgroundProcess: 3 };
});

describe("WorkQueueCard", () => {
  it("answers the queues which wait above the inventory", () => {
    render(<WorkQueueCard />);
    expect(
      screen.getByRole("heading", { name: "dashboard.workQueue.title" }),
    ).toBeInTheDocument();
    expect(screen.getByText("dashboard.workQueue.alerts")).toBeInTheDocument();
    expect(
      screen.getByText("dashboard.workQueue.updateReviews"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("dashboard.workQueue.runningWork"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("dashboard.workQueue.failedWork"),
    ).toBeInTheDocument();
  });

  it("counts every queue by the api with the filter its link carries", () => {
    render(<WorkQueueCard />);
    expect(state.asked).toEqual([
      {
        resource: "ServiceAlert",
        filter: undefined,
        sort: { field: "severity,-occurredAt", order: "ASC" },
      },
      {
        resource: "ServiceAlert",
        filter: { category: "update_review_required" },
        sort: { field: "severity,-occurredAt", order: "ASC" },
      },
      {
        resource: "BackgroundProcess",
        filter: { status: "pending,running" },
        sort: undefined,
      },
      {
        resource: "BackgroundProcess",
        filter: { status: "failed" },
        sort: undefined,
      },
    ]);
  });

  it("answers the total of the api and not the records of a page", () => {
    state.totals = { ServiceAlert: 42, BackgroundProcess: 5 };
    render(<WorkQueueCard />);
    expect(screen.getAllByText("42")).toHaveLength(2);
    expect(screen.getAllByText("5")).toHaveLength(2);
  });

  it("asks the alerts of all categories and the reviews of one category", () => {
    const [alerts, reviews] = workQueues();
    expect(alerts.filter).toBeUndefined();
    expect(reviews.resource).toBe(alerts.resource);
    expect(reviews.filter).not.toEqual(alerts.filter);
  });

  it("counts a queue which answers nothing at zero", () => {
    state.totals = {};
    render(<WorkQueueCard />);
    expect(screen.getAllByText("0")).toHaveLength(4);
  });
});
