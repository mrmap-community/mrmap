import { type ReactNode } from "react";

import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ShowBackgroundProcess, {
  IS_STALE_CHECK_INTERVAL_SECONDS,
  STALE_AFTER_MILLISECONDS,
} from "./ShowBackgroundProcess";

type Listener = (message: {
  payload?: { records?: Record<string, unknown>[] };
}) => void;

const state = vi.hoisted(() => ({
  /** the realtime bus topics the screen listens to, by topic */
  listeners: new Map<string, Listener>(),
  /** what the show controller answers; a test sets it before it renders */
  controller: {
    record: { id: "1", status: "running" } as Record<string, unknown>,
    refetch: vi.fn(),
    isFetching: false,
    isPending: false,
  },
}));

vi.mock("react-admin", () => ({
  useResourceContext: () => "BackgroundProcess",
  useDataProvider: () => ({
    subscribe: (topic: string, listener: Listener) => {
      state.listeners.set(topic, listener);
    },
    unsubscribe: (topic: string) => {
      state.listeners.delete(topic);
    },
  }),
  useShowController: () => state.controller,
  ShowContextProvider: ({ children }: { children?: ReactNode }) => (
    <>{children}</>
  ),
  ShowView: ({ children }: { children?: ReactNode }) => <>{children}</>,
  SimpleShowLayout: ({ children }: { children?: ReactNode }) => (
    <>{children}</>
  ),
  TextField: () => null,
  DateField: () => null,
  NumberField: () => null,
  // the phase field renders through FunctionField; the stub renders the
  // screen's render callback over the shown record, and the translate stub
  // answers the key it was asked for - which is what these specs assert,
  // while the i18n specs prove both languages carry the words
  FunctionField: ({
    render: renderField,
  }: {
    render: (record: Record<string, unknown>) => ReactNode;
  }) => <>{renderField(state.controller.record)}</>,
  useTranslate:
    () =>
    (key: string) =>
      key,
}));

vi.mock("../../Field/ProgressField", () => ({ default: () => null }));
vi.mock("../../Field/RelatedResourceField", () => ({ default: () => null }));
vi.mock("../../Field/DurationField", () => ({ default: () => null }));
vi.mock("./BackgroundProcessLogs", () => ({ default: () => null }));
vi.mock("./ProcessStatusField", () => ({ default: () => null }));

/** the tick of the provider, in milliseconds - the interval of seconds it is
 *  given as a prop, turned into the milliseconds of a timer */
const TICK_MILLISECONDS = IS_STALE_CHECK_INTERVAL_SECONDS * 1000;

/** push the shown process over the realtime bus, as the provider receives it */
const pushRecord = () => {
  const listener = state.listeners.get("resource/BackgroundProcess/1");
  act(() => {
    listener?.({ payload: { records: [{ id: "1", status: "running" }] } });
  });
};

beforeEach(() => {
  vi.useFakeTimers();
  state.listeners.clear();
  state.controller = {
    record: { id: "1", status: "running" },
    refetch: vi.fn(),
    isFetching: false,
    isPending: false,
  };
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ShowBackgroundProcess", () => {
  it("names the threshold with the milliseconds of an interval, not with its seconds", () => {
    // one second is not ten milliseconds: a threshold read in milliseconds
    // which equals the tick is the record's age when the tick fires, so the
    // bug of #1086 - every running process older than ten milliseconds -
    // would refetch on every push
    expect(STALE_AFTER_MILLISECONDS).toBe(TICK_MILLISECONDS);
  });

  it("asks the bus for the shown process, by its id", () => {
    render(<ShowBackgroundProcess />);
    expect(state.listeners.has("resource/BackgroundProcess/1")).toBe(true);
  });

  it("lets a pushed record stand over one whole tick", () => {
    render(<ShowBackgroundProcess />);
    pushRecord();
    // on the tick after the push the record is exactly one interval old,
    // which is not older than the threshold - the push was fresh and the
    // screen must answer it instead of refetching it away
    act(() => {
      vi.advanceTimersByTime(TICK_MILLISECONDS);
    });
    expect(state.controller.refetch).not.toHaveBeenCalled();
  });

  it("refetches when the last push grew older than the interval it names", () => {
    render(<ShowBackgroundProcess />);
    pushRecord();
    act(() => {
      vi.advanceTimersByTime(2 * TICK_MILLISECONDS);
    });
    expect(state.controller.refetch).toHaveBeenCalledOnce();
  });

  it("never refetches a process which has ended", () => {
    state.controller = {
      record: { id: "1", status: "completed" },
      refetch: vi.fn(),
      isFetching: false,
      isPending: false,
    };
    render(<ShowBackgroundProcess />);
    act(() => {
      vi.advanceTimersByTime(3 * TICK_MILLISECONDS);
    });
    expect(state.controller.refetch).not.toHaveBeenCalled();
  });

  it("looks the reported phase up as a key of the background activity", () => {
    // the api answers the registration's phases as keys (#1267); the screen
    // asks the translations for `backgroundActivity.phases.<key>` and the
    // stub of this spec answers with the key it was given
    state.controller = {
      record: { id: "1", status: "running", phase: "collect_metadata_records" },
      refetch: vi.fn(),
      isFetching: false,
      isPending: false,
    };
    const { getByText } = render(<ShowBackgroundProcess />);
    expect(
      getByText("backgroundActivity.phases.collect_metadata_records"),
    ).toBeInTheDocument();
  });
});
