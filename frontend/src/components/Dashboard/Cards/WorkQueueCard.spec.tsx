import type { ReactNode } from "react";
import type { SortPayload } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WorkQueueCard, { workQueues } from "./WorkQueueCard";

/** what the read of one count answered */
interface Answer {
  state: "loading" | "zero" | "value" | "forbidden" | "error";
  total?: number;
}

const QUEUES = workQueues();

const state = vi.hoisted(() => ({
  /** what the count of a queue asked the api for, recorded once per queue */
  asked: {} as Record<
    string,
    { resource: string; filter?: Record<string, unknown>; sort?: SortPayload }
  >,
  /** the link the number of a queue answers, which must carry its own filter */
  links: {} as Record<string, string | undefined>,
  /** the answer per queue key, defaulting to a read which has not answered yet */
  answers: {} as Record<string, Answer>,
  health: "healthy",
}));

/** the queue a count belongs to, derived from the very filter it asked with */
const keyOf = (resource: string, filter?: Record<string, unknown>) =>
  workQueues().find(
    (queue) =>
      queue.resource === resource &&
      JSON.stringify(queue.filter ?? null) === JSON.stringify(filter ?? null),
  )?.key ?? "";

vi.mock("../../../jsonapi/components/Count", () => ({
  Count: ({
    resource,
    filter,
    sort,
    onStateChange,
  }: {
    resource: string;
    filter?: Record<string, unknown>;
    sort?: SortPayload;
    onStateChange?: (state: string, total?: number) => void;
  }) => {
    const key = keyOf(resource, filter);
    state.asked[key] = { resource, filter, sort };
    state.links[key] = filter ? `filter=${JSON.stringify(filter)}` : undefined;
    const answer = state.answers[key] ?? { state: "loading" as const };
    onStateChange?.(answer.state, answer.total);
    return (
      <a href={`/${resource}/list`}>
        {answer.state === "value"
          ? answer.total
          : answer.state === "zero"
            ? 0
            : ""}
      </a>
    );
  },
}));

vi.mock("../../../context/SystemStatusContext", () => ({
  useSystemStatus: () => ({ health: state.health }),
}));

vi.mock("../../Resource/BackgroundProcess/ListBackgroundProcess", () => ({
  // the api answers the statuses of a process as a comma separated list
  ACTIVE_STATUSES: "pending,running",
}));

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
  useCreatePath:
    () =>
    ({ resource }: { resource: string }) =>
      `/${resource}/list`,
  Link: ({ children }: { to: unknown; children?: ReactNode }) => (
    <span>{children}</span>
  ),
}));

vi.mock("../../MUI/SimpleCard", () => ({
  default: ({
    title,
    subheader,
    children,
  }: {
    title?: ReactNode;
    subheader?: ReactNode;
    children?: ReactNode;
  }) => (
    <section>
      <h2>{title}</h2>
      <p>{subheader}</p>
      {children}
    </section>
  ),
}));

/** the rows of the card, in the order of `workQueues()` */
const row = (key: string) =>
  screen.getByText(`dashboard.workQueue.${key}`).closest("li") as HTMLElement;

/** the color of the chip a row answers with - the assertion against a state of
 *  nothing being answered as success */
const chipColor = (key: string) =>
  (
    row(key)
      .querySelector(".MuiChip-root")
      ?.className.match(/MuiChip-color(\w+)/)?.[1] ?? "none"
  ).toLowerCase();

/** the word the chip of a row answers */
const chipLabel = (key: string) =>
  row(key).querySelector(".MuiChip-root")?.textContent ?? "";

/** every queue answered the same state, which is how a card of nothing is built */
const allQueues = (answer: Answer) =>
  Object.fromEntries(QUEUES.map((queue) => [queue.key, answer]));

const READ_EMPTY = { state: "zero", total: 0 } as const;

beforeEach(() => {
  state.asked = {};
  state.links = {};
  state.answers = {};
  state.health = "healthy";
});

describe("WorkQueueCard", () => {
  it("answers the queues of the deployment as one compact card", () => {
    render(<WorkQueueCard />);
    expect(
      screen.getByRole("heading", { name: "systemStatus.title" }),
    ).toBeInTheDocument();
    for (const queue of QUEUES) {
      expect(
        screen.getByText(`dashboard.workQueue.${queue.key}`),
      ).toBeInTheDocument();
      expect(chipLabel(queue.key)).toBe("systemStatus.checking");
    }
    // one card with one header: the queues are rows of it and never banners of
    // their own, so the card stays as compact as its rows are (#1816)
    expect(screen.getAllByRole("heading")).toHaveLength(1);
    expect(screen.getAllByRole("listitem")).toHaveLength(QUEUES.length);
  });

  it("counts every queue by the api with the filter its link carries", () => {
    render(<WorkQueueCard />);
    expect(state.asked).toEqual({
      runningWork: {
        resource: "BackgroundProcess",
        filter: { status: "pending,running" },
        sort: undefined,
      },
      runningHarvests: {
        resource: "BackgroundProcess",
        filter: { status: "pending,running", process_type: "harvesting" },
        sort: undefined,
      },
      updateReviews: {
        resource: "ServiceAlert",
        filter: { category: "update_review_required" },
        sort: { field: "severity,-occurredAt", order: "ASC" },
      },
      harvestAlerts: {
        // the states of the harvesting with one request, of the kind of
        // service which is harvested at all (#1086)
        resource: "ServiceAlert",
        filter: {
          category:
            "harvest_aborted,harvest_incomplete,harvest_overdue,harvest_schedule_too_tight",
          serviceType: "CatalogueService",
        },
        sort: { field: "severity,-occurredAt", order: "ASC" },
      },
      failedWork: {
        resource: "BackgroundProcess",
        filter: { status: "failed" },
        sort: undefined,
      },
    });
  });

  it("navigates a queue to the very records its count answered", () => {
    render(<WorkQueueCard />);
    for (const queue of QUEUES) {
      // the number and the label of a row ask the list of the resource of the
      // queue, with the filter the count itself was asked with
      const link = row(queue.key).querySelector("a")!;
      expect(link.getAttribute("href")).toBe(`/${queue.resource}/list`);
      expect(state.links[queue.key]).toEqual(
        queue.filter ? `filter=${JSON.stringify(queue.filter)}` : undefined,
      );
    }
    const harvest = JSON.parse(
      (state.links.harvestAlerts ?? "").replace("filter=", ""),
    );
    expect(harvest).toMatchObject({ serviceType: "CatalogueService" });
  });

  it("names the category of every alerts queue, because the attention card already asks all alerts", () => {
    // a queue of all alerts would ask the records the attention card reads with
    // useServiceAlerts a second time, which is a duplicate request (#1816)
    expect(QUEUES).toHaveLength(5);
    for (const queue of QUEUES.filter((it) => it.resource === "ServiceAlert")) {
      expect(queue.filter).toHaveProperty("category");
    }
    expect(QUEUES.some((queue) => queue.filter === undefined)).toBe(false);
  });

  it("counts the overlapping queues apart and never adds them up", () => {
    const [running, harvests, reviews, harvestAlerts, failed] = QUEUES;
    // every update review and every harvesting alert is an alert of a service,
    // so the queues overlap and answer rows of their own instead of a sum
    expect(reviews.resource).toBe(harvestAlerts.resource);
    expect(reviews.filter).not.toEqual(harvestAlerts.filter);
    expect(harvestAlerts.filter).toMatchObject({
      serviceType: "CatalogueService",
    });
    expect(running.kind).toBe("running");
    expect(harvests.kind).toBe("running");
    expect(failed.kind).toBe("attention");

    state.answers = {
      ...allQueues(READ_EMPTY),
      updateReviews: { state: "value", total: 7 },
      harvestAlerts: { state: "value", total: 3 },
      failedWork: { state: "value", total: 1 },
    };
    render(<WorkQueueCard />);
    // each number answers its own row, none of them a sum of the others
    expect(row("updateReviews").querySelector("a")?.textContent).toBe("7");
    expect(row("harvestAlerts").querySelector("a")?.textContent).toBe("3");
    expect(row("failedWork").querySelector("a")?.textContent).toBe("1");
    expect(screen.queryByText("11")).not.toBeInTheDocument();
  });

  it("distinguishes the queue which is loading from the queue which is idle", () => {
    state.answers = {
      ...allQueues(READ_EMPTY),
      runningWork: { state: "loading" },
    };
    render(<WorkQueueCard />);
    // the loading row answers waiting, not the word of a queue which was read
    // and found empty, and its number answers nothing
    expect(chipLabel("runningWork")).toBe("systemStatus.checking");
    expect(chipLabel("runningHarvests")).toBe("dashboard.workQueue.idle");
    expect(row("runningWork").querySelector("a")?.textContent).toBe("");
    expect(chipColor("runningWork")).toBe("default");
    expect(chipColor("runningHarvests")).toBe("default");
  });

  it("distinguishes a queue nobody may read from a queue which holds nothing", () => {
    state.answers = {
      ...allQueues(READ_EMPTY),
      failedWork: { state: "forbidden" },
    };
    render(<WorkQueueCard />);
    // a refused read answers its own word and never the word of an empty queue,
    // so a missing permission is never read as nothing to do
    expect(chipLabel("failedWork")).toBe("dashboard.workQueue.notPermitted");
    expect(chipLabel("updateReviews")).toBe("dashboard.workQueue.none");
    expect(chipColor("failedWork")).toBe("default");
    expect(chipColor("failedWork")).not.toBe("success");
  });

  it("distinguishes a queue the api refused from a queue which holds nothing", () => {
    state.answers = {
      ...allQueues(READ_EMPTY),
      runningWork: { state: "error" },
    };
    render(<WorkQueueCard />);
    expect(chipLabel("runningWork")).toBe("dashboard.workQueue.unreadable");
    expect(chipColor("runningWork")).toBe("error");
    expect(chipLabel("runningHarvests")).toBe("dashboard.workQueue.idle");
    expect(chipLabel("failedWork")).toBe("dashboard.workQueue.none");
  });

  it("answers the records which wait and the work which runs", () => {
    state.answers = {
      runningWork: { state: "value", total: 3 },
      runningHarvests: { state: "value", total: 1 },
      updateReviews: { state: "value", total: 12 },
      harvestAlerts: READ_EMPTY,
      failedWork: { state: "value", total: 4 },
    };
    render(<WorkQueueCard />);
    expect(row("runningWork").querySelector("a")?.textContent).toBe("3");
    expect(row("updateReviews").querySelector("a")?.textContent).toBe("12");
    expect(chipLabel("runningWork")).toBe("dashboard.workQueue.running");
    expect(chipLabel("updateReviews")).toBe("dashboard.workQueue.waiting");
    // an empty attention queue answers nothing, never the word of waiting work
    expect(chipLabel("harvestAlerts")).toBe("dashboard.workQueue.none");
    // a queue which waits is answered by its severity and never as success
    expect(chipColor("runningWork")).toBe("primary");
    expect(chipColor("updateReviews")).toBe("warning");
    expect(chipColor("harvestAlerts")).toBe("default");
  });

  it("answers failed work in the color of an error", () => {
    state.answers = {
      ...allQueues(READ_EMPTY),
      failedWork: { state: "value", total: 2 },
    };
    render(<WorkQueueCard />);
    expect(chipLabel("failedWork")).toBe("dashboard.workQueue.waiting");
    expect(chipColor("failedWork")).toBe("error");
  });

  it("never answers healthy while a queue was not read", () => {
    // the queues which were read all answer nothing, but one of them could not
    // be read at all: the card answers apart and never as a healthy deployment
    state.answers = {
      ...allQueues(READ_EMPTY),
      failedWork: { state: "error" },
    };
    render(<WorkQueueCard />);
    expect(
      screen.getByText("dashboard.workQueue.scope.partial"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("dashboard.workQueue.scope.healthy"),
    ).not.toBeInTheDocument();
    expect(chipColor("failedWork")).toBe("error");
  });

  it("answers the scope of the card by the state of all its queues", () => {
    state.answers = allQueues(READ_EMPTY);
    const { unmount } = render(<WorkQueueCard />);
    // only a status which says so and queues which were all read answer healthy
    expect(
      screen.getByText("dashboard.workQueue.scope.healthy"),
    ).toBeInTheDocument();
    unmount();

    state.answers = {
      ...allQueues(READ_EMPTY),
      runningWork: { state: "value", total: 2 },
    };
    render(<WorkQueueCard />);
    expect(
      screen.getByText("dashboard.workQueue.scope.running"),
    ).toBeInTheDocument();
    unmount();

    state.answers = {
      ...allQueues(READ_EMPTY),
      updateReviews: { state: "value", total: 2 },
    };
    render(<WorkQueueCard />);
    expect(
      screen.getByText("dashboard.workQueue.scope.watch"),
    ).toBeInTheDocument();
    unmount();

    state.answers = allQueues({ state: "forbidden" });
    render(<WorkQueueCard />);
    expect(
      screen.getByText("dashboard.workQueue.scope.unreadable"),
    ).toBeInTheDocument();
  });

  it("answers a deployment whose machinery does not run above every queue", () => {
    // every count reads nothing and the counts alone would answer a deployment
    // without a problem, but the workers do not run: the card must say so (#833)
    state.answers = allQueues(READ_EMPTY);
    state.health = "down";
    render(<WorkQueueCard />);
    expect(
      screen.getByText("dashboard.workQueue.scope.down"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("dashboard.workQueue.scope.healthy"),
    ).not.toBeInTheDocument();
  });

  it("reads the machinery from the context the app bar polls and asks nothing of its own", () => {
    render(<WorkQueueCard />);
    // the only reads of the card are the counts of its queues - the state of the
    // deployment comes from the shared context of the app bar (#833)
    expect(Object.keys(state.asked)).toEqual(QUEUES.map((queue) => queue.key));
  });
});
