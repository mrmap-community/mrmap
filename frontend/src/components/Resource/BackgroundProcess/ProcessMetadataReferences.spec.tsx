import { type ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProcessMetadataReferences from "./ProcessMetadataReferences";

const state = vi.hoisted(() => ({
  /** the shown background process */
  record: undefined as Record<string, unknown> | undefined,
  /** the row the mocked columns render */
  row: undefined as Record<string, unknown> | undefined,
  /** the props the panel hands to the list which fetches the rows */
  listProps: undefined as Record<string, unknown> | undefined,
  /** the props the retry column hands to the button */
  retryProps: undefined as Record<string, unknown> | undefined,
}));

vi.mock("react-admin", () => ({
  useRecordContext: () => state.record,
  useTranslate: () => (key: string) => key,
  DateField: () => null,
  TextField: () => null,
  // the columns read their row from the record context in the real list; the
  // mock hands them the row the test declares
  FunctionField: ({ render }: { render: (record: unknown) => ReactNode }) => (
    <>{render(state.row)}</>
  ),
}));

vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: (props: Record<string, unknown> & { columns?: ReactNode[] }) => {
    state.listProps = props;
    return <>{props.columns}</>;
  },
}));

vi.mock("../../Field/TruncatedTextField", () => ({ default: () => null }));
vi.mock("../../Lists/CustomListActions", () => ({ default: () => null }));

vi.mock("./RetryReferenceButton", () => ({
  REFERENCE_FAILED_STATE: 2,
  default: (props: Record<string, unknown>) => {
    state.retryProps = props;
    return null;
  },
}));

beforeEach(() => {
  state.record = {
    id: "12",
    status: "completed",
    state: "completed",
    doneAt: "2026-11-13T09:05:00Z",
    referencesTotal: 4,
    referencesFailed: 1,
  };
  state.row = undefined;
  state.listProps = undefined;
  state.retryProps = undefined;
});

describe("ProcessMetadataReferences", () => {
  it("asks the flat collection scoped by the shown process", () => {
    render(<ProcessMetadataReferences />);
    const listProps = state.listProps as Record<string, unknown>;
    expect(listProps.resource).toEqual("TemporaryMdMetadataFile");
    expect(listProps.filter).toEqual({ background_process__id: "12" });
    expect(listProps.sort).toEqual({ field: "requestId", order: "DESC" });
    expect(listProps.storeKey).toBe(false);
    // a decided process does not poll its table
    expect(listProps.refetchInterval).toBe(false);
  });

  it("keeps a running process table fresh", () => {
    state.record = { ...state.record, doneAt: undefined, status: "running" };
    render(<ProcessMetadataReferences />);
    expect((state.listProps as Record<string, unknown>).refetchInterval).toBe(
      5000,
    );
  });

  it("renders nothing for a process which planned no references", () => {
    state.record = { id: "12", status: "completed" };
    const { container } = render(<ProcessMetadataReferences />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the skipped, retried and failed states with the harvest words", () => {
    for (const [rowState, word] of [
      [0, "harvestRun.collectingStates.skipped"],
      [1, "backgroundActivity.references.states.retrying"],
      [2, "harvestRun.collectingStates.failed"],
    ] as const) {
      state.row = { id: 1, state: rowState };
      const { unmount } = render(<ProcessMetadataReferences />);
      expect(screen.getByText(word)).toBeInTheDocument();
      unmount();
    }
  });

  it("answers the error kind with the word keyed after it", () => {
    state.row = { id: 1, state: 2, errorKind: "fetch_unreachable" };
    render(<ProcessMetadataReferences />);
    expect(
      screen.getByText(
        "backgroundActivity.references.errorKinds.fetch_unreachable",
      ),
    ).toBeInTheDocument();
  });

  it("says nothing where no failure was named", () => {
    state.row = { id: 1, state: 1 };
    const { container } = render(<ProcessMetadataReferences />);
    // only the state chip renders: no error-kind wording
    expect(container.querySelectorAll(".MuiChip-root")).toHaveLength(1);
  });

  it("lets the retry column act for a failed row of a running decision", () => {
    state.row = { id: 1, state: 2 };
    render(<ProcessMetadataReferences />);
    expect(state.retryProps).toEqual({ retryable: true });
  });

  it("closes the retry column for a process which ended failed", () => {
    state.record = { ...state.record, status: "failed", state: "failed" };
    state.row = { id: 1, state: 2 };
    render(<ProcessMetadataReferences />);
    expect(state.retryProps).toEqual({ retryable: false });
  });
});
