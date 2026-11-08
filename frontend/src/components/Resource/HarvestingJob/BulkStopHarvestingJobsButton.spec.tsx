import type { RaRecord } from "react-admin";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BulkStopHarvestingJobsButton from "./BulkStopHarvestingJobsButton";

import "@testing-library/jest-dom/vitest";

const state = vi.hoisted(() => ({
  data: [] as RaRecord[],
  selectedIds: [] as string[],
  update: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
  unselect: vi.fn(),
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
  useListContext: () => ({ data: state.data, selectedIds: state.selectedIds }),
  useNotify: () => state.notify,
  useRefresh: () => state.refresh,
  useResourceDefinition: () => ({ hasEdit: true }),
  useTranslate: () => (key: string) => key.split(".").pop(),
  useUnselect: () => state.unselect,
  useUpdate: () => [state.update, { isPending: false }],
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
  state.data = [
    { id: "41", doneAt: null },
    { id: "40", doneAt: null },
    { id: "39", doneAt: "2026-11-05T08:48:03Z" },
  ];
  state.selectedIds = ["41", "40", "39"];
  state.update = vi.fn().mockResolvedValue({ data: { id: "41" } });
});

const openAsk = () => {
  render(<BulkStopHarvestingJobsButton />);
  fireEvent.click(screen.getByRole("button", { name: "bulkStopTitle" }));
  return within(screen.getByRole("dialog"));
};

describe("stopping the selected harvesting runs", () => {
  it("sends the stop of a row for every selected run which did not end", async () => {
    const dialog = openAsk();
    expect(dialog.getByText("bulkStopContent")).toBeInTheDocument();
    fireEvent.click(dialog.getByRole("button", { name: "bulkStopTitle" }));
    await waitFor(() => expect(state.update).toHaveBeenCalledTimes(2));
    expect(state.update).toHaveBeenNthCalledWith(
      1,
      "HarvestingJob",
      expect.objectContaining({ id: "41", data: { phase: 4711 } }),
      expect.anything(),
    );
    expect(state.update).toHaveBeenNthCalledWith(
      2,
      "HarvestingJob",
      expect.objectContaining({ id: "40", data: { phase: 4711 } }),
      expect.anything(),
    );
    expect(state.notify).toHaveBeenCalledWith("harvestRun.list.bulkStopped", {
      type: "info",
      messageArgs: { smart_count: 2, count: 2 },
    });
    expect(state.unselect).toHaveBeenCalledWith(["41", "40"]);
    expect(state.refresh).toHaveBeenCalledOnce();
  });

  it("names the runs the api refused to stop", async () => {
    state.update = vi
      .fn()
      .mockImplementation((_resource: string, params: { id: string }) =>
        params.id === "40"
          ? Promise.reject(new Error("already ended"))
          : Promise.resolve({ data: params }),
      );
    const dialog = openAsk();
    fireEvent.click(dialog.getByRole("button", { name: "bulkStopTitle" }));
    await waitFor(() =>
      expect(state.notify).toHaveBeenCalledWith("harvestRun.list.bulkStopRefused", {
        type: "warning",
        messageArgs: { ids: "40" },
      }),
    );
    expect(state.notify).toHaveBeenCalledWith("harvestRun.list.bulkStopped", {
      type: "warning",
      messageArgs: { smart_count: 1, count: 1 },
    });
  });

  it("answers an error when nothing of the selection could be stopped", async () => {
    state.update = vi.fn().mockRejectedValue(new Error("forbidden"));
    const dialog = openAsk();
    fireEvent.click(dialog.getByRole("button", { name: "bulkStopTitle" }));
    await waitFor(() =>
      expect(state.notify).toHaveBeenCalledWith("harvestRun.list.bulkStopRefused", {
        type: "error",
        messageArgs: { ids: "41, 40" },
      }),
    );
    expect(state.notify).not.toHaveBeenCalledWith(
      "harvestRun.list.bulkStopped",
      expect.anything(),
    );
  });
});
