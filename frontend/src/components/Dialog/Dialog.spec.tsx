import { fireEvent, render, renderHook, screen } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { describe, expect, it, vi } from "vitest";
import Dialog from "./Dialog";
import DialogHeader from "./DialogHeader";
import { context } from "./DialogContextBase";
import useDialogMutationSuccess from "./useDialogMutationSuccess";

const mocks = vi.hoisted(() => ({ refetch: vi.fn(), notify: vi.fn() }));
vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
  useListContext: () => ({ refetch: mocks.refetch }),
  useResourceContext: () => "Service",
  useNotify: () => mocks.notify,
}));
const close = vi.fn();
const value = {
  isOpen: true,
  title: "Title",
  content: "Default content",
  actions: <button>Save</button>,
  open: vi.fn(),
  close,
};
const wrapper = ({ children }: PropsWithChildren) => (
  <context.Provider value={value}>{children}</context.Provider>
);

describe("shared dialogs", () => {
  it("renders one set of sections and honours explicit empty content", () => {
    const { rerender } = render(<Dialog />, { wrapper });
    expect(screen.getAllByText("Title")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Save" })).toHaveLength(1);
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Title");
    expect(screen.getByRole("dialog")).toHaveAccessibleDescription(
      "Default content",
    );
    rerender(<Dialog>{null}</Dialog>);
    expect(screen.queryByText("Default content")).not.toBeInTheDocument();
  });
  it("renders the shared header with an accessible close button", () => {
    render(<DialogHeader>Edit service</DialogHeader>, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "ra.action.close" }));
    expect(close).toHaveBeenCalled();
  });
  it("refreshes, closes, and sends the current action notification", () => {
    const { result, rerender } = renderHook(
      ({ action }: { action: "created" | "deleted" }) =>
        useDialogMutationSuccess(action),
      { wrapper, initialProps: { action: "created" } },
    );
    result.current();
    expect(mocks.refetch).toHaveBeenCalled();
    expect(mocks.notify).toHaveBeenLastCalledWith(
      "resources.Service.notifications.created",
      expect.objectContaining({ type: "success" }),
    );
    rerender({ action: "deleted" });
    result.current();
    expect(mocks.notify).toHaveBeenLastCalledWith(
      "resources.Service.notifications.deleted",
      expect.objectContaining({ undoable: false }),
    );
  });
});
