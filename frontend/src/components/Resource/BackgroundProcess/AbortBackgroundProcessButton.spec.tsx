import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AbortBackgroundProcessButton from "./AbortBackgroundProcessButton";

const state = vi.hoisted(() => ({
  record: undefined as Record<string, unknown> | undefined,
  refused: false,
  update: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("react-admin", () => ({
  useRecordContext: () => state.record,
  useTranslate: () => (key: string) => key,
  useNotify: () => state.notify,
  useRefresh: () => state.refresh,
  // the update of react admin answers through the callbacks of its options,
  // which no data provider would answer here
  useUpdate: () => [
    (
      resource: string,
      params: unknown,
      options?: { onSuccess?: () => void; onError?: () => void },
    ) => {
      state.update(resource, params);
      if (state.refused) {
        options?.onError?.();
      } else {
        options?.onSuccess?.();
      }
    },
    { isPending: false },
  ],
}));

beforeEach(() => {
  state.record = undefined;
  state.refused = false;
  state.update = vi.fn();
  state.notify = vi.fn();
  state.refresh = vi.fn();
});

const abortButton = () =>
  screen.queryByRole("button", { name: "backgroundActivity.abort" });

describe("AbortBackgroundProcessButton", () => {
  it("asks the api to abort the process the record reports about", async () => {
    state.record = { id: 12, status: "running" };
    render(<AbortBackgroundProcessButton />);
    fireEvent.click(abortButton() as HTMLElement);
    expect(state.update).toHaveBeenCalledWith(
      "BackgroundProcess",
      expect.objectContaining({
        id: 12,
        data: { phase: "abort" },
        previousData: state.record,
      }),
    );
    await waitFor(() =>
      expect(state.notify).toHaveBeenCalledWith(
        "backgroundActivity.abortAsked",
        { type: "info" },
      ),
    );
    expect(state.refresh).toHaveBeenCalled();
  });

  it("tells the user when the api refused the abort", async () => {
    state.record = { id: 12, status: "pending" };
    state.refused = true;
    render(<AbortBackgroundProcessButton />);
    fireEvent.click(abortButton() as HTMLElement);
    await waitFor(() =>
      expect(state.notify).toHaveBeenCalledWith(
        "backgroundActivity.abortFailed",
        { type: "error" },
      ),
    );
  });

  it("offers no abort for a process which did end", () => {
    for (const status of ["completed", "failed", "aborted"]) {
      state.record = { id: 12, status };
      const { unmount } = render(<AbortBackgroundProcessButton />);
      expect(abortButton()).toBeNull();
      unmount();
    }
  });
});
