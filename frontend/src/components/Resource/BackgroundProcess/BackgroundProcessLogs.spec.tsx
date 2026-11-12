import { type ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BackgroundProcessLogs from "./BackgroundProcessLogs";

const state = vi.hoisted(() => ({
  record: undefined as Record<string, unknown> | undefined,
  /** the props the section hands to the list base which fetches the logs */
  listProps: undefined as Record<string, unknown> | undefined,
  list: {
    data: [] as Record<string, unknown>[],
    isPending: false,
    error: undefined as unknown,
    refetch: vi.fn(),
  },
}));

vi.mock("react-admin", () => ({
  useRecordContext: () => state.record,
  useTranslate: () => (key: string) => key,
  useListContext: () => state.list,
  ListBase: (props: Record<string, unknown>) => {
    state.listProps = props;
    const { children } = props as { children?: ReactNode };
    return <>{children}</>;
  },
  Button: ({
    children,
    onClick,
  }: {
    children?: ReactNode;
    onClick?: () => void;
  }) => <button onClick={onClick}>{children}</button>,
}));

vi.mock("../../Field/RelativeDateField", () => ({ default: () => null }));

beforeEach(() => {
  state.record = { id: "42" };
  state.listProps = undefined;
  state.list = {
    data: [],
    isPending: false,
    error: undefined,
    refetch: vi.fn(),
  };
});

describe("BackgroundProcessLogs", () => {
  it("asks the nested route of the shown process for its logs, newest first", () => {
    render(<BackgroundProcessLogs />);

    const listProps = state.listProps as Record<string, Record<string, unknown>>;
    expect(listProps.resource).toEqual("BackgroundProcessLog");
    expect(listProps.filter).toEqual({ backgroundProcess: "42" });
    expect(listProps.sort).toEqual({ field: "date", order: "DESC" });
    expect(listProps.disableSyncWithLocation).toBe(true);
    expect(listProps.queryOptions).toEqual({
      meta: { relatedResource: { resource: "BackgroundProcess", id: "42" } },
    });
  });

  it("renders nothing without a shown process", () => {
    state.record = undefined;
    const { container } = render(<BackgroundProcessLogs />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says that a process reported nothing", () => {
    render(<BackgroundProcessLogs />);
    expect(screen.getByText("backgroundActivity.log.empty")).toBeInTheDocument();
  });

  it("refetches from its error instead of hiding the log", () => {
    state.list = {
      ...state.list,
      error: new Error("boom"),
    };
    render(<BackgroundProcessLogs />);
    screen.getByText("backgroundActivity.log.loadError");
    screen.getByRole("button").click();
    expect(state.list.refetch).toHaveBeenCalledOnce();
  });

  it("renders one row per report with its type and text", () => {
    state.list = {
      ...state.list,
      data: [
        { id: "2", logType: "error", description: "the import died", date: "2026-11-09T10:00:00Z" },
        { id: "1", logType: "warning", description: "a page was skipped", date: "2026-11-09T09:00:00Z" },
      ],
    };
    render(<BackgroundProcessLogs />);
    expect(screen.getByText("the import died")).toBeInTheDocument();
    expect(screen.getByText("a page was skipped")).toBeInTheDocument();
    expect(screen.getByText("backgroundActivity.log.type.error")).toBeInTheDocument();
    expect(screen.getByText("backgroundActivity.log.type.warning")).toBeInTheDocument();
  });
});
