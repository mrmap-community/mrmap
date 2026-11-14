import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RetryReferenceButton from "./RetryReferenceButton";

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

const retryButton = () =>
  screen.queryByRole("button", {
    name: "backgroundActivity.references.retry",
  });

describe("RetryReferenceButton", () => {
  it("asks the api to retry the failed reference the record reports about", async () => {
    state.record = { id: 42, state: 2 };
    render(<RetryReferenceButton />);
    fireEvent.click(retryButton() as HTMLElement);
    expect(state.update).toHaveBeenCalledWith(
      "TemporaryMdMetadataFile",
      expect.objectContaining({
        id: 42,
        data: { retry: true },
        previousData: state.record,
      }),
    );
    await waitFor(() =>
      expect(state.notify).toHaveBeenCalledWith(
        "backgroundActivity.references.retryAsked",
        { type: "info" },
      ),
    );
    expect(state.refresh).toHaveBeenCalled();
  });

  it("tells the user when the api refused the retry", async () => {
    state.record = { id: 42, state: 2 };
    state.refused = true;
    render(<RetryReferenceButton />);
    fireEvent.click(retryButton() as HTMLElement);
    await waitFor(() =>
      expect(state.notify).toHaveBeenCalledWith(
        "backgroundActivity.references.retryFailed",
        { type: "error" },
      ),
    );
  });

  it("offers no retry for a row which is not failed", () => {
    for (const rowState of [0, 1]) {
      state.record = { id: 42, state: rowState };
      const { unmount } = render(<RetryReferenceButton />);
      expect(retryButton()).toBeNull();
      unmount();
    }
  });

  it("offers no retry while the process behind the row is closed", () => {
    state.record = { id: 42, state: 2 };
    render(<RetryReferenceButton retryable={false} />);
    expect(retryButton()).toBeNull();
  });
});
