import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RunHarvestingButton from "./RunHarvestingButton";

const state = vi.hoisted(() => ({
  create: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
  hasCreate: true,
  identity: { id: "user-1" } as { id: string } | undefined,
  isPending: false,
}));
vi.mock("react-admin", () => ({
  Button: ({
    label,
    disabled,
    onClick,
  }: {
    label: string;
    disabled: boolean;
    onClick: () => void;
  }) => (
    <button disabled={disabled} onClick={onClick}>
      {label}
    </button>
  ),
  useCreate: () => [state.create, { isPending: state.isPending }],
  useGetIdentity: () => ({ data: state.identity }),
  useResourceDefinition: () => ({ hasCreate: state.hasCreate }),
  useNotify: () => state.notify,
  useRefresh: () => state.refresh,
}));
beforeEach(() => {
  vi.clearAllMocks();
  state.hasCreate = true;
  state.identity = { id: "user-1" };
  state.isPending = false;
});
describe("RunHarvestingButton", () => {
  it("creates a harvest for this catalogue and reports success", () => {
    render(<RunHarvestingButton serviceId="csw-1" />);
    fireEvent.click(screen.getByRole("button"));
    expect(state.create).toHaveBeenCalledWith(
      "HarvestingJob",
      { data: { service: { id: "csw-1" } } },
      expect.anything(),
    );
    state.create.mock.calls[0][2].onSuccess();
    expect(state.notify).toHaveBeenCalledWith("harvestingSchedules.queued", {
      type: "success",
    });
    expect(state.refresh).toHaveBeenCalledOnce();
  });
  it("reports rejected requests without claiming harvesting started", () => {
    render(<RunHarvestingButton serviceId="csw-1" />);
    fireEvent.click(screen.getByRole("button"));
    state.create.mock.calls[0][2].onError();
    expect(state.notify).toHaveBeenCalledWith("harvestingSchedules.failed", {
      type: "error",
    });
  });
  it("disables submission while a request is pending", () => {
    state.isPending = true;
    render(<RunHarvestingButton serviceId="csw-1" />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
  it("hides the action for anonymous users", () => {
    state.identity = undefined;
    render(<RunHarvestingButton serviceId="csw-1" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
  it("hides the action when creation is unavailable", () => {
    state.hasCreate = false;
    render(<RunHarvestingButton serviceId="csw-1" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
