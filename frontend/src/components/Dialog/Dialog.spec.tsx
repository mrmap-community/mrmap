import type { PropsWithChildren } from "react";
import { useState } from "react";

import { fireEvent, render, renderHook, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ContextBasedDialog from "./Dialog";
import { context, DialogBase, useDialogContextBase } from "./DialogContextBase";
import DialogHeader from "./DialogHeader";
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
    const { rerender } = render(<ContextBasedDialog />, { wrapper });
    expect(screen.getAllByText("Title")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Save" })).toHaveLength(1);
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Title");
    expect(screen.getByRole("dialog")).toHaveAccessibleDescription(
      "Default content",
    );
    rerender(<ContextBasedDialog>{null}</ContextBasedDialog>);
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

// The controlled mode and the live updates of the shared shell.

const ControlledHarness = ({ onClose = vi.fn() }: { onClose?: () => void }) => {
  const [title, setTitle] = useState("First title");
  return (
    <>
      <button onClick={() => setTitle("Second title")}>rename</button>
      <ContextBasedDialog
        open
        onClose={onClose}
        title={title}
        content={<p>controlled content</p>}
        actions={<button>Apply</button>}
        maxWidth="sm"
      />
    </>
  );
};

describe("controlled dialogs", () => {
  it("renders its sections and replaces them on rerender while open", () => {
    render(<ControlledHarness />);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAccessibleName("First title");
    expect(dialog).toHaveTextContent("controlled content");
    // forwarded MUI props reach the paper
    expect(
      document.querySelector(".MuiDialog-paperWidthSm"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "rename", hidden: true }),
    );
    expect(dialog).toHaveAccessibleName("Second title");
  });

  it("dismisses through the callers callback", () => {
    const onClose = vi.fn();
    render(<ControlledHarness onClose={onClose} />);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("omits the sections which answer nothing", () => {
    render(<ContextBasedDialog open title="Only a title" />);
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Only a title");
    expect(screen.queryByText("Default content")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps separate instances isolated", () => {
    render(
      <>
        <DialogBase>
          <Opener which="one" />
          <ContextBasedDialog />
        </DialogBase>
        <DialogBase>
          <Opener which="two" />
          <ContextBasedDialog />
        </DialogBase>
      </>,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // an open modal aria-hides the sibling react roots, so the openers are
    // queried including hidden elements
    fireEvent.click(
      screen.getByRole("button", { name: "open one", hidden: true }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "open two", hidden: true }),
    );
    const dialogs = screen.getAllByRole("dialog", { hidden: true });
    expect(dialogs).toHaveLength(2);
    expect(dialogs[0]).toHaveTextContent("one");
    expect(dialogs[1]).toHaveTextContent("two");
    // replacing the content of one instance while open leaves the other one untouched
    fireEvent.click(
      screen.getByRole("button", { name: "replace one", hidden: true }),
    );
    expect(
      screen.getAllByRole("dialog", { hidden: true })[0],
    ).toHaveTextContent("new one");
    expect(
      screen.getAllByRole("dialog", { hidden: true })[1],
    ).not.toHaveTextContent("new one");
  });
});

const Opener = ({ which }: { which: string }) => {
  const { open } = useDialogContextBase();
  return (
    <>
      <button onClick={() => open(`Title ${which}`, `${which} content`, null)}>
        open {which}
      </button>
      <button onClick={() => open(`Title ${which}`, `new ${which}`, null)}>
        replace {which}
      </button>
    </>
  );
};
