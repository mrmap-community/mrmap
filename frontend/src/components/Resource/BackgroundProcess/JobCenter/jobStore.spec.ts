import { describe, expect, it } from "vitest";

import {
  applyRecords,
  clearCompleted,
  groupJobs,
  hasProgressTotal,
  isActive,
  jobStateOf,
  MAX_TRACKED_JOBS,
  removeJob,
  trim,
  visibleJobs,
  type BackgroundJobRecord,
  initialJobStoreState,
} from "./jobStore";

/** a process as the api answers it, with the fields the center reads */
const record = (
  id: number | string,
  status: string,
  overrides: Partial<BackgroundJobRecord> = {},
): BackgroundJobRecord => ({
  id,
  status,
  processType: "harvesting",
  description: `harvesting run ${id}`,
  phase: "running",
  dateCreated: `2026-11-0${1 + (Number(id) % 8)}T12:00:00Z`,
  ...overrides,
  ...(status !== "pending" && status !== "running"
    ? { doneAt: "2026-11-09T12:00:00Z" }
    : {}),
});

describe("jobStateOf", () => {
  it("prefers the normalized state of the contract", () => {
    expect(jobStateOf(record(1, "running", { state: "retrying" }))).toBe(
      "retrying",
    );
    expect(jobStateOf(record(1, "running", { state: "queued" }))).toBe(
      "queued",
    );
  });

  it("falls back to the status of an older api and decorates the retry", () => {
    expect(jobStateOf(record(1, "pending"))).toBe("queued");
    expect(jobStateOf(record(1, "running"))).toBe("running");
    expect(jobStateOf(record(1, "running", { isRetrying: true }))).toBe(
      "retrying",
    );
    expect(jobStateOf(record(1, "failed"))).toBe("failed");
    expect(jobStateOf(record(1, "completed"))).toBe("completed");
    expect(jobStateOf(record(1, "aborted"))).toBe("aborted");
  });

  it("treats a retrying state as active", () => {
    expect(isActive(record(1, "running", { state: "retrying" }))).toBe(true);
    expect(isActive(record(1, "completed"))).toBe(false);
  });
});

describe("applyRecords", () => {
  it("keys by the id as string so bus and list events meet", () => {
    const { state } = applyRecords(initialJobStoreState(), [
      record(1, "running"),
    ]);
    const { state: updated } = applyRecords(state, [
      record("1", "completed"),
    ]);

    expect(Object.keys(updated.jobs)).toEqual(["1"]);
    expect(updated.jobs["1"].status).toBe("completed");
  });

  it("announces a failure exactly once over duplicated events", () => {
    const failing = record(1, "failed", { state: "failed" });
    const { state, transitions } = applyRecords(initialJobStoreState(), [
      record(1, "running"),
    ]);
    expect(transitions.failed).toHaveLength(0);

    const first = applyRecords(state, [failing]);
    expect(first.transitions.failed).toHaveLength(1);

    // the same message arrives again (debounce dropped one, the sender
    // repeated the other): the terminal state is already there
    const second = applyRecords(first.state, [failing]);
    expect(second.transitions.failed).toHaveLength(0);
  });

  it("never lets a late progress event pull back a terminal process", () => {
    const { state } = applyRecords(initialJobStoreState(), [
      record(1, "failed"),
    ]);
    const late = applyRecords(state, [record(1, "running")]);

    expect(late.state.jobs["1"].status).toBe("failed");
    expect(late.transitions.failed).toHaveLength(0);
  });

  it("counts each completion once for the aggregated announcement", () => {
    let state = applyRecords(initialJobStoreState(), [
      record(1, "running"),
      record(2, "running"),
    ]).state;

    const first = applyRecords(state, [
      record(1, "completed"),
      record(2, "completed"),
      record(1, "completed"),
    ]);
    expect(first.transitions.completed).toHaveLength(2);

    const second = applyRecords(first.state, [
      record(1, "completed"),
      record(2, "completed"),
    ]);
    expect(second.transitions.completed).toHaveLength(0);
    state = second.state;
    expect(Object.keys(state.jobs)).toHaveLength(2);
  });

  it("announces a process which is already failed on arrival only once", () => {
    // hydration answers recent failures without announcing - this is the live
    // path where a create event carries an already failed process (created and
    // failed between the last page and the subscription)
    const failing = record(1, "failed");
    const { transitions } = applyRecords(initialJobStoreState(), [failing]);
    expect(transitions.failed).toHaveLength(1);
  });

  it("ignores records without an id", () => {
    const { state, transitions } = applyRecords(initialJobStoreState(), [
      { status: "failed" } as BackgroundJobRecord,
    ]);
    expect(state.jobs).toEqual({});
    expect(transitions.failed).toHaveLength(0);
  });
});

describe("removeJob", () => {
  it("drops the deleted process", () => {
    const { state } = applyRecords(initialJobStoreState(), [record(1, "done")]);
    const removed = removeJob(state, "1");
    expect(removed.jobs).toEqual({});
    expect(removeJob(removed, "1")).toBe(removed);
  });
});

describe("trim", () => {
  it("keeps every active process when possible and drops oldest terminal ones", () => {
    const many: BackgroundJobRecord[] = [];
    for (let id = 0; id < MAX_TRACKED_JOBS + 50; id++) {
      many.push(
        record(
          id,
          id < 10 ? "running" : "completed",
          {},
        ),
      );
    }

    const { state } = applyRecords(initialJobStoreState(), many);
    const kept = Object.values(state.jobs);

    expect(kept.length).toBeLessThanOrEqual(MAX_TRACKED_JOBS);
    kept
      .filter((job) => job.status === "running")
      .forEach((job) => expect(job.status).toBe("running"));
    // the active ones survived in full
    expect(kept.filter((job) => job.status === "running")).toHaveLength(10);
  });

  it("answers the untouched state while below the cap", () => {
    const { state } = applyRecords(initialJobStoreState(), [
      record(1, "running"),
    ]);
    expect(trim(state)).toBe(state);
  });

  it("survives a burst of more than a thousand active processes", () => {
    const burst: BackgroundJobRecord[] = [];
    for (let id = 0; id < 1200; id++) {
      burst.push(record(id, "running"));
    }
    const { state } = applyRecords(initialJobStoreState(), burst);
    expect(Object.keys(state.jobs).length).toBeLessThanOrEqual(
      MAX_TRACKED_JOBS,
    );
  });
});

describe("visibleJobs", () => {
  const jobs = [
    record(1, "running", {
      description: "Hamburger Metadatenkatalog",
      dateCreated: "2026-11-05T12:00:00Z",
    }),
    record(2, "pending", { dateCreated: "2026-11-06T12:00:00Z" }),
    record(3, "failed", { dateCreated: "2026-11-04T12:00:00Z" }),
    record(4, "completed", { dateCreated: "2026-11-03T12:00:00Z" }),
    record(5, "running", {
      processType: "update",
      description: "WMS Update Topo",
      dateCreated: "2026-11-07T12:00:00Z",
    }),
  ];
  const state = { jobs: Object.fromEntries(jobs.map((j) => [String(j.id), j])) };

  it("shows every state on the all tab, newest first", () => {
    expect(visibleJobs(state, "all", "").map((j) => j.id)).toEqual([
      5, 2, 1, 3, 4,
    ]);
  });

  it("counts retrying work as running", () => {
    const retrying = record(6, "running", {
      state: "retrying",
      dateCreated: "2026-11-08T12:00:00Z",
    });
    const withRetry = {
      jobs: { ...state.jobs, ["6"]: retrying },
    };
    expect(visibleJobs(withRetry, "running", "").map((j) => j.id)).toEqual([
      6, 5, 1,
    ]);
  });

  it("narrows by the search over the wording the row renders", () => {
    expect(
      visibleJobs(state, "all", "Hamburger").map((j) => j.id),
    ).toEqual([1]);
    expect(visibleJobs(state, "failed", "update").map((j) => j.id)).toEqual(
      [],
    );
    expect(
      visibleJobs(state, "failed", "").map((j) => j.id),
    ).toEqual([3]);
  });
});

describe("groupJobs", () => {
  it("groups by the related resource and puts typeless processes apart", () => {
    // the drawer hands the groups the newest-first order of visibleJobs and
    // groupJobs keeps it: records within a group stay as they were given
    const groups = groupJobs([
      record(2, "running", {
        relatedResource: { type: "WebMapService", id: "aaaa1111-2222" },
        dateCreated: "2026-11-06T12:00:00Z",
      }),
      record(1, "running", {
        relatedResource: { type: "WebMapService", id: "aaaa1111-2222" },
        dateCreated: "2026-11-05T12:00:00Z",
      }),
      record(3, "running", { dateCreated: "2026-11-04T12:00:00Z" }),
    ]);

    expect(groups.map((g) => g.key)).toEqual([
      "WebMapService/aaaa1111-2222",
      "harvesting",
    ]);
    expect(groups[0].records.map((r) => r.id)).toEqual([2, 1]);
  });
});

describe("clearCompleted", () => {
  it("drops completed processes from the view and keeps the rest", () => {
    const { state } = applyRecords(initialJobStoreState(), [
      record(1, "completed"),
      record(2, "failed"),
      record(3, "running"),
    ]);
    const cleared = clearCompleted(state);

    expect(Object.keys(cleared.jobs)).toEqual(["2", "3"]);
  });
});

describe("hasProgressTotal", () => {
  it("demands a real denominator for a determinate bar", () => {
    expect(hasProgressTotal(record(1, "running", { totalSteps: 4 }))).toBe(
      true,
    );
    expect(hasProgressTotal(record(1, "running", { totalSteps: null }))).toBe(
      false,
    );
    expect(
      hasProgressTotal(record(1, "running", { totalSteps: undefined })),
    ).toBe(false);
    expect(hasProgressTotal(record(1, "running", { totalSteps: 0 }))).toBe(
      false,
    );
  });
});
