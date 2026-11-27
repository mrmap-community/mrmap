import type {
  BackgroundJobRecord,
  JobStoreState,
  ProcessesAnswer,
  StoreWindow,
} from "../../Resource/BackgroundProcess/JobCenter/jobStore";

import type { ReactNode } from "react";

import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BackgroundProcessesCard, { MAX_ROWS } from "./BackgroundProcessesCard";

/** what one window of the store answered */
interface WindowAnswer {
  isPending?: boolean;
  error?: unknown;
  records?: BackgroundJobRecord[];
}

const state = vi.hoisted(() => ({
  hydrated: true,
  active: { records: [] } as WindowAnswer,
  recent: { records: [] } as WindowAnswer,
  totals: {
    active: undefined as number | undefined,
    recent: undefined as number | undefined,
  },
}));

const toWindow = (answer: WindowAnswer): StoreWindow => ({
  isPending: answer.isPending ?? false,
  error: answer.error ?? null,
  records: answer.records ?? [],
});

vi.mock(
  "../../Resource/BackgroundProcess/JobCenter/BackgroundJobCenterContext",
  () => ({
    useBackgroundJobCenter: () => ({
      state: {
        jobs: Object.fromEntries(
          [
            ...(state.active.records ?? []),
            ...(state.recent.records ?? []),
          ].map((record) => [String(record.id), record]),
        ),
      } as JobStoreState,
      windows: {
        active: toWindow(state.active),
        recent: toWindow(state.recent),
      },
      totals: state.totals,
      hydrated: state.hydrated,
      open: false,
      setOpen: vi.fn(),
      clearCompleted: vi.fn(),
      subscribeFailed: vi.fn(),
    }),
  }),
);

vi.mock("react-admin", async () => {
  const React = await vi.importActual<typeof import("react")>("react");
  const RecordContext = React.createContext<
    Record<string, unknown> | undefined
  >(undefined);
  return {
    RecordContext,
    useRecordContext: () => React.useContext(RecordContext),
    // the shared fields of a row read their value from the record of that very
    // row, which is what makes the chip of a row the chip of the drawer
    useFieldValue: ({ source }: { source: string }) =>
      React.useContext(RecordContext)?.[source],
    useTranslate: () => (key: string, options?: Record<string, unknown>) =>
      options !== undefined && options._ !== undefined
        ? String(options._)
        : key,
    useCreatePath:
      () =>
      ({
        resource,
        type,
        id,
      }: {
        resource: string;
        type: string;
        id?: string | number;
      }) =>
        type === "show" ? `/${resource}/${id}/show` : `/${resource}/list`,
    Link: ({
      to,
      children,
      ...props
    }: {
      to: { pathname: string; search?: string } | string;
      children?: ReactNode;
    } & Record<string, unknown>) => {
      // the same rule react-router applies: a search is separated by "?"
      const path =
        typeof to === "string"
          ? to
          : `${to.pathname}${
              to.search ? `?${to.search.replace(/^\?/, "")}` : ""
            }`;
      return (
        <a href={path} {...props}>
          {children}
        </a>
      );
    },
  };
});

/** the moment of a row: the source it reads, or the word of no moment */
vi.mock("../../Field/RelativeDateField", async () => {
  const ra = await vi.importMock<typeof import("react-admin")>("react-admin");
  return {
    default: ({
      source,
      emptyText,
    }: {
      source: string;
      emptyText?: ReactNode;
    }) => {
      const record = ra.useRecordContext() as
        Record<string, unknown> | undefined;
      const value = record?.[source];
      return value === null || value === undefined ? (
        <span>{emptyText}</span>
      ) : (
        <span>{`moment:${source}`}</span>
      );
    },
  };
});

const process = (
  id: number,
  status: string,
  overrides: Partial<BackgroundJobRecord> = {},
): BackgroundJobRecord => ({
  id,
  status,
  processType: "harvesting",
  description: `harvesting run ${id}`,
  dateCreated: "2026-11-09T12:00:00Z",
  ...(status === "pending" ? {} : { doneAt: "2026-11-09T12:30:00Z" }),
  ...overrides,
});

/** the rows of the table, without the header row; a table the card cannot
 *  answer is no table at all, which is what these assertions are about */
const rows = () => screen.queryAllByRole("row").slice(1);
/** the row of one process, addressed by the link of its title */
const rowOf = (id: number) =>
  screen
    .getByRole("link", { name: `harvesting run ${id}` })
    .closest("tr") as HTMLElement;
/** the color of the status chip a row answers with */
const chipColor = (id: number) =>
  (
    rowOf(id)
      .querySelector(".MuiChip-root")
      ?.className.match(/MuiChip-color(\w+)/)?.[1] ?? "none"
  ).toLowerCase();
/** how often the card answers one scope sentence: in its subheader, and once
 *  more as the alert which replaces a table the card cannot answer */
const scopeAnswers = (answer: ProcessesAnswer) =>
  screen.queryAllByText(`dashboard.backgroundProcesses.scope.${answer}`, {
    exact: true,
  });
/** the scope the card answers with, which must be exactly one */
const scopeIs = (answer: ProcessesAnswer) => {
  expect(scopeAnswers(answer)).toHaveLength(1);
  for (const other of ALL_ANSWERS.filter((it) => it !== answer)) {
    expect(scopeAnswers(other)).toHaveLength(0);
  }
};

const READ_NOTHING: WindowAnswer = { records: [] };

const ALL_ANSWERS: ProcessesAnswer[] = [
  "loading",
  "forbidden",
  "error",
  "partial",
  "empty",
  "running",
  "waiting",
  "history",
];

beforeEach(() => {
  state.hydrated = true;
  state.active = { ...READ_NOTHING };
  state.recent = { ...READ_NOTHING };
  state.totals = { active: 0, recent: 0 };
});

describe("BackgroundProcessesCard", () => {
  it("answers the work of the deployment as one compact table of four columns", () => {
    state.active = { records: [process(1, "running")] };
    render(<BackgroundProcessesCard />);
    expect(
      screen.getByRole("heading", {
        name: "dashboard.backgroundProcesses.title",
      }),
    ).toBeInTheDocument();
    for (const column of ["type", "status", "started", "progress"]) {
      expect(
        screen.getByRole("columnheader", {
          name: `dashboard.backgroundProcesses.${column}`,
        }),
      ).toBeInTheDocument();
    }
    expect(rows()).toHaveLength(1);
    // the process type is read from the record, the raw value answering for a
    // type the translations do not name
    expect(rowOf(1)).toHaveTextContent("harvesting");
    // the state chip is the shared field of the resource, in the color of its
    // state and with the word of the background activity
    expect(chipColor(1)).toBe("info");
    expect(within(rowOf(1)).getByText("running")).toBeInTheDocument();
  });

  it("bounds its rows and points at the list which answers all of them", () => {
    state.active = {
      records: Array.from({ length: MAX_ROWS + 4 }, (_, index) =>
        process(index + 1, "running", {
          dateCreated: `2026-11-09T12:00:${String(index).padStart(2, "0")}Z`,
        }),
      ),
    };
    state.totals = { active: 40, recent: 12 };
    render(<BackgroundProcessesCard />);
    expect(rows()).toHaveLength(MAX_ROWS);
    // the bounded view says so beside the link which opens the complete list
    expect(
      screen.getByText("dashboard.backgroundProcesses.bounded"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "backgroundActivity.viewAll" }),
    ).toHaveAttribute("href", "/BackgroundProcess/list");
  });

  it("does not name a bounded number when the totals are not known", () => {
    state.active = { records: [process(1, "running")] };
    state.totals = { active: undefined, recent: undefined };
    render(<BackgroundProcessesCard />);
    expect(
      screen.queryByText("dashboard.backgroundProcesses.bounded"),
    ).not.toBeInTheDocument();
  });

  it("distinguishes the work which runs from the work which waits", () => {
    state.active = {
      records: [
        process(1, "running"),
        process(2, "pending", { dateCreated: undefined, doneAt: null }),
      ],
    };
    render(<BackgroundProcessesCard />);
    scopeIs("running");
    // a queued process answers the word of a start which did not happen yet and
    // the neutral chip of the contract
    expect(
      within(rowOf(2)).getByText("dashboard.backgroundProcesses.notStarted"),
    ).toBeInTheDocument();
    expect(chipColor(2)).toBe("default");
    // work which moves reads the moment of its start
    expect(
      within(rowOf(1)).getByText("moment:dateCreated"),
    ).toBeInTheDocument();
  });

  it("answers waiting work when nothing moves", () => {
    state.active = { records: [process(2, "pending")] };
    render(<BackgroundProcessesCard />);
    scopeIs("waiting");
  });

  it("marks the decided work of the history window apart from live work", () => {
    // the store holds one failure which decided before this page load and one
    // which failed live: only the live one may read as work which is broken now
    state.active = { records: [process(1, "failed", { state: "failed" })] };
    state.recent = {
      records: [
        process(2, "failed", { state: "failed" }),
        process(3, "completed"),
      ],
    };
    state.totals = { active: 1, recent: 2 };
    render(<BackgroundProcessesCard />);
    expect(
      within(rowOf(2)).getByText("dashboard.backgroundProcesses.failedBefore"),
    ).toBeInTheDocument();
    expect(
      within(rowOf(3)).getByText("dashboard.backgroundProcesses.decidedBefore"),
    ).toBeInTheDocument();
    // decided work reads the moment of its decision, not of its start
    expect(within(rowOf(3)).getByText("moment:doneAt")).toBeInTheDocument();
    // the live failure is counted and links to the queue of failed work
    expect(
      screen.getByRole("link", {
        name: "dashboard.backgroundProcesses.justFailed",
      }),
    ).toHaveAttribute(
      "href",
      '/BackgroundProcess/list?filter={"status":"failed,aborted"}',
    );
    expect(chipColor(1)).toBe("error");
    expect(chipColor(3)).toBe("success");
  });

  it("counts only the live failures beside a table of history", () => {
    state.recent = { records: [process(2, "failed", { state: "failed" })] };
    render(<BackgroundProcessesCard />);
    // a failure of the history window is an event of the past: the queues card
    // counts the failed work of the api and this panel never competes with it
    scopeIs("history");
    expect(
      screen.queryByRole("link", {
        name: "dashboard.backgroundProcesses.justFailed",
      }),
    ).not.toBeInTheDocument();
  });

  it("answers a store which holds nothing without claiming a healthy deployment", () => {
    render(<BackgroundProcessesCard />);
    scopeIs("empty");
    expect(
      screen.getByText("dashboard.backgroundProcesses.none"),
    ).toBeInTheDocument();
    expect(rows()).toHaveLength(0);
    expect(
      screen.queryByRole("link", {
        name: "dashboard.backgroundProcesses.justFailed",
      }),
    ).not.toBeInTheDocument();
  });

  it("distinguishes the table which is loading from the table which is empty", () => {
    state.active = { isPending: true };
    state.recent = { isPending: true };
    render(<BackgroundProcessesCard />);
    // a read which has not answered yet never shows a table of nothing ...
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(
      screen.queryByText("dashboard.backgroundProcesses.none"),
    ).not.toBeInTheDocument();
    // ... and answers its own sentence instead of the word of a deployment
    // without work
    scopeIs("loading");
    expect(document.querySelectorAll(".MuiSkeleton-root")).toHaveLength(2);
  });

  it("distinguishes a table nobody may read from a table which is empty", () => {
    // #1803 and #1804: a caller without the right stays on the dashboard and
    // reads the refusal, never an empty deployment
    state.active = { error: { status: 403 } };
    state.recent = { error: { status: 401 } };
    render(<BackgroundProcessesCard />);
    const alert = screen.getByRole("status");
    expect(alert).toHaveTextContent(
      "dashboard.backgroundProcesses.scope.forbidden",
    );
    expect(alert.className).toContain("MuiAlert-colorInfo");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    // the refusal answers itself, never a broken api and never an empty table
    expect(scopeAnswers("error")).toHaveLength(0);
    expect(scopeAnswers("empty")).toHaveLength(0);
    expect(scopeAnswers("forbidden")).toHaveLength(2);
  });

  it("distinguishes a table the api refused from a table nobody may read", () => {
    state.active = { error: new Error("unreachable") };
    state.recent = { error: new Error("unreachable") };
    render(<BackgroundProcessesCard />);
    const alert = screen.getByRole("status");
    expect(alert).toHaveTextContent(
      "dashboard.backgroundProcesses.scope.error",
    );
    expect(alert.className).toContain("MuiAlert-colorError");
    // a broken api is answered as what it is: not a missing permission
    expect(scopeAnswers("forbidden")).toHaveLength(0);
    expect(scopeAnswers("error")).toHaveLength(2);
  });

  it("answers a half read table as partial and never as the whole answer", () => {
    // the window of the running work answered nothing and the history window was
    // refused: "nothing runs" is exactly what the refused window cannot tell
    state.active = { ...READ_NOTHING };
    state.recent = { error: { status: 403 } };
    render(<BackgroundProcessesCard />);
    expect(
      screen.getByText("dashboard.backgroundProcesses.partialBadge"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    // a half read table answers itself and never the answer of the half it read
    expect(scopeAnswers("empty")).toHaveLength(0);
    expect(scopeAnswers("partial")).toHaveLength(2);
  });

  it("answers a numeric progress only when the process reports a denominator", () => {
    state.active = {
      records: [
        process(1, "running", { progress: 42, totalSteps: 10, doneSteps: 4 }),
        process(2, "running", { progress: 0, totalSteps: null }),
        process(3, "completed", { progress: null, totalSteps: null }),
      ],
    };
    render(<BackgroundProcessesCard />);
    // authoritative data answers the share ...
    expect(within(rowOf(1)).getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "42",
    );
    expect(rowOf(1)).toHaveTextContent("42%");
    expect(rowOf(1)).not.toHaveTextContent(
      "dashboard.backgroundProcesses.unknown",
    );
    // ... work which moves without one answers a moving bar and the word
    expect(within(rowOf(2)).getByRole("progressbar")).not.toHaveAttribute(
      "aria-valuenow",
    );
    expect(rowOf(2)).toHaveTextContent("dashboard.backgroundProcesses.unknown");
    expect(rowOf(2)).not.toHaveTextContent("%");
    // ... decided work which reported nothing answers the word and no bar
    expect(within(rowOf(3)).queryByRole("progressbar")).not.toBeInTheDocument();
    expect(rowOf(3)).toHaveTextContent(
      "dashboard.backgroundProcesses.notReported",
    );
  });

  it("keeps a reported share inside the range a bar can answer", () => {
    state.active = {
      records: [process(1, "running", { progress: 140, totalSteps: 4 })],
    };
    render(<BackgroundProcessesCard />);
    // a value above the range of a bar never renders as 140 percent
    expect(within(rowOf(1)).getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
    expect(rowOf(1)).toHaveTextContent("100%");
  });

  it("links a row to the show screen of its process", () => {
    state.active = { records: [process(1, "running")] };
    render(<BackgroundProcessesCard />);
    expect(
      screen.getByRole("link", { name: "harvesting run 1" }),
    ).toHaveAttribute("href", "/BackgroundProcess/1/show");
  });

  it("answers the title of a process which reports none", () => {
    state.active = {
      records: [process(1, "running", { description: undefined })],
    };
    render(<BackgroundProcessesCard />);
    // the id of the process answers, as the drawer does, and never an empty row
    expect(
      screen.getByRole("link", { name: "backgroundActivity.process" }),
    ).toHaveAttribute("href", "/BackgroundProcess/1/show");
  });

  it("answers nothing at all without a session", () => {
    // #833: the processes are operator data; a visitor without a session never
    // sees a panel which can only read "not permitted"
    state.hydrated = false;
    state.active = { error: { status: 401 } };
    const { container } = render(<BackgroundProcessesCard />);
    expect(container).toBeEmptyDOMElement();
  });
});
