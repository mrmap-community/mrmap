import { fireEvent, render, screen } from "@testing-library/react";
import type { RaRecord } from "react-admin";
import { beforeEach, describe, expect, it, vi } from "vitest";
import HarvestingJobActions from "./HarvestingJobActions";

const state = vi.hoisted(() => ({
  run: { id: 1 } as RaRecord,
  create: vi.fn(),
  update: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
  redirect: vi.fn(),
  isPending: false,
}));
vi.mock("react-admin", () => ({
  useRecordContext: () => state.run,
  useCreate: () => [state.create, { isPending: state.isPending }],
  useUpdate: () => [state.update, { isPending: state.isPending }],
  useNotify: () => state.notify,
  useRefresh: () => state.refresh,
  useRedirect: () => state.redirect,
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
      {label}
    </button>
  ),
  TopToolbar: ({ children }: { children: React.ReactNode }) => children,
  PrevNextButtons: () => null,
}));
beforeEach(() => {
  vi.clearAllMocks();
  state.isPending = false;
  state.run = {
    id: 1,
    service: { id: "csw-1" },
    harvestDatasets: false,
    harvestServices: true,
    maxStepSize: 25,
    doneAt: null,
  };
});
describe("harvesting run actions", () => {
  it("only offers stop for an active run and refreshes after stopping", () => {
    render(<HarvestingJobActions />);
    fireEvent.click(screen.getByRole("button", { name: "harvestRun.stop" }));
    expect(screen.queryByText("harvestRun.restart")).not.toBeInTheDocument();
    expect(state.update).toHaveBeenCalledWith(
      "HarvestingJob",
      expect.objectContaining({ id: 1, data: { phase: 4711 } }),
      expect.anything(),
    );
    state.update.mock.calls[0][2].onSuccess();
    expect(state.refresh).toHaveBeenCalledOnce();
  });
  it("restarts a terminated run with its existing configuration", () => {
    state.run.doneAt = "2026-10-08T10:00:00Z";
    render(<HarvestingJobActions />);
    fireEvent.click(screen.getByRole("button", { name: "harvestRun.restart" }));
    expect(screen.queryByText("harvestRun.stop")).not.toBeInTheDocument();
    expect(state.create).toHaveBeenCalledWith(
      "HarvestingJob",
      {
        data: {
          service: { id: "csw-1" },
          harvestDatasets: false,
          harvestServices: true,
          maxStepSize: 25,
        },
      },
      expect.anything(),
    );
    state.create.mock.calls[0][2].onSuccess({ id: 2 });
    expect(state.redirect).toHaveBeenCalledWith("show", "HarvestingJob", 2);
  });
  it("reports a stop failure", () => {
    render(<HarvestingJobActions />);
    fireEvent.click(screen.getByRole("button"));
    state.update.mock.calls[0][2].onError();
    expect(state.notify).toHaveBeenCalledWith("harvestRun.stopFailed", {
      type: "error",
    });
  });
  it("prevents repeated submissions while pending", () => {
    state.isPending = true;
    render(<HarvestingJobActions />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
