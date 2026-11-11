import type { RaRecord } from "react-admin";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import StopHarvestingJobButton, { ABORT_PHASE } from "./StopHarvestingJobButton";

import "@testing-library/jest-dom/vitest";

const state = vi.hoisted(() => ({
  run: { id: "41" } as RaRecord,
  hasEdit: true,
  isPending: false,
  update: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("react-admin", () => ({
  Button: ({
    label,
    onClick,
    disabled,
  }: {
    label: string;
    onClick: () => void;
    disabled: boolean;
  }) => (
    <button onClick={onClick} disabled={disabled}>
      {label.split(".").pop()}
    </button>
  ),
  useNotify: () => state.notify,
  useRecordContext: () => state.run,
  useRefresh: () => state.refresh,
  useResourceDefinition: () => ({ hasEdit: state.hasEdit }),
  useTranslate: () => (key: string) => key.split(".").pop(),
  useUpdate: () => [state.update, { isPending: state.isPending }],
}));

vi.mock("../../Dialog/Dialog", () => ({
  default: ({
    open,
    title,
    actions,
    children,
  }: {
    open: boolean;
    title: React.ReactNode;
    actions: React.ReactNode;
    children: React.ReactNode;
  }) =>
    open ? (
      <div role="dialog">
        {title}
        {children}
        {actions}
      </div>
    ) : null,
}));

vi.mock("../../Dialog/DialogHeader", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

beforeEach(() => {
  vi.clearAllMocks();
  state.hasEdit = true;
  state.isPending = false;
  state.run = { id: "41", doneAt: null };
  state.update = vi.fn().mockResolvedValue({ data: { id: "41" } });
});

const openAsk = () => {
  render(<StopHarvestingJobButton />);
  fireEvent.click(screen.getByRole("button", { name: "stop" }));
  return within(screen.getByRole("dialog"));
};

describe("stopping a harvesting run from its row", () => {
  it("asks before it sends the mutation the show screen sends", async () => {
    const dialog = openAsk();
    expect(dialog.getByText("stopConfirmTitle")).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "stop" }));
    await waitFor(() =>
      expect(state.update).toHaveBeenCalledWith(
        "HarvestingJob",
        expect.objectContaining({
          id: "41",
          data: { phase: ABORT_PHASE },
        }),
        expect.objectContaining({ mutationMode: "pessimistic" }),
      ),
    );
    expect(state.notify).toHaveBeenCalledWith("harvestRun.list.stopAsked", {
      type: "info",
    });
    expect(state.refresh).toHaveBeenCalledOnce();
  });

  it("tells a stop the api refused", async () => {
    state.update = vi.fn().mockRejectedValue(new Error("forbidden"));
    const dialog = openAsk();
    fireEvent.click(dialog.getByRole("button", { name: "stop" }));
    await waitFor(() =>
      expect(state.notify).toHaveBeenCalledWith("harvestRun.stopFailed", {
        type: "error",
      }),
    );
    expect(state.refresh).not.toHaveBeenCalled();
  });

  it("offers no stop to a run which ended", () => {
    state.run = { id: "37", doneAt: "2026-11-05T08:48:03Z" };
    render(<StopHarvestingJobButton />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("offers no stop to a caller which may not change the run", () => {
    state.hasEdit = false;
    render(<StopHarvestingJobButton />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
