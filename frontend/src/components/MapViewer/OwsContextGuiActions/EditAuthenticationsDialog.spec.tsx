import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OWSContext } from "../../../ows-lib/OwsContext/core";
import EditAuthenticationsDialog from "./EditAuthenticationsDialog";

const state = vi.hoisted(() => ({ context: undefined as OWSContext | undefined, update: vi.fn() }));
vi.mock("../../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  useOwsContextBase: () => ({ owsContext: state.context, updateOwsContext: state.update }),
}));
beforeEach(() => { state.context = new OWSContext(); state.update.mockClear(); });

describe("authentication editor", () => {
  it("saves entered credentials while retaining the context methods", () => {
    const close = vi.fn();
    render(<EditAuthenticationsDialog open setOpen={close} />);
    fireEvent.change(screen.getByLabelText(/Get Capabilities URL/), { target: { value: "https://example.com/wms" } });
    fireEvent.change(screen.getByLabelText(/Username/), { target: { value: "reader" } });
    fireEvent.change(screen.getByLabelText(/Password/), { target: { value: "test-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    const saved = state.update.mock.calls[0][0];
    expect(saved).toBeInstanceOf(OWSContext);
    expect(saved.authentications).toEqual([{ getCapabilitiesUrl: "https://example.com/wms", username: "reader", password: "test-password" }]);
    expect(close).toHaveBeenCalledWith(false);
    expect(state.context?.authentications).toBeUndefined();
  });
  it("discards unsaved additions when reopened", () => {
    const close = vi.fn();
    const { rerender } = render(<EditAuthenticationsDialog open setOpen={close} />);
    fireEvent.change(screen.getByLabelText(/Get Capabilities URL/), { target: { value: "https://example.com/unsaved" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    rerender(<EditAuthenticationsDialog open={false} setOpen={close} />);
    rerender(<EditAuthenticationsDialog open setOpen={close} />);
    expect(screen.queryByText("https://example.com/unsaved")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Get Capabilities URL/)).toHaveValue("");
    expect(state.update).not.toHaveBeenCalled();
  });
});
