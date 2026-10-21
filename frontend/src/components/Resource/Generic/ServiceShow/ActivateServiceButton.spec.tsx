import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ActivateServiceButton from "./ActivateServiceButton";

const state = vi.hoisted(() => ({
  resource: "WebMapService",
  record: undefined as Record<string, unknown> | undefined,
  updatable: true,
  operationId: undefined as string | undefined,
  refused: false,
  isPending: false,
  update: vi.fn(),
  notify: vi.fn(),
  refresh: vi.fn(),
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
  useRecordContext: () => state.record,
  useResourceContext: () => state.resource,
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
    { isPending: state.isPending },
  ],
}));

vi.mock("../../../../jsonapi/hooks/useOperation", () => ({
  default: (operationId: string) => {
    state.operationId = operationId;
    return state.updatable ? {} : undefined;
  },
}));

beforeEach(() => {
  state.resource = "WebMapService";
  state.record = undefined;
  state.updatable = true;
  state.operationId = undefined;
  state.refused = false;
  state.isPending = false;
  state.update = vi.fn();
  state.notify = vi.fn();
  state.refresh = vi.fn();
});

const activationButton = (name: string) =>
  screen.queryByRole("button", { name });

describe("ActivateServiceButton", () => {
  it("activates a deactivated service of any registered protocol", () => {
    for (const resource of [
      "WebMapService",
      "WebFeatureService",
      "CatalogueService",
    ]) {
      state.resource = resource;
      state.record = { id: `${resource}-1`, isActive: false };
      const { unmount } = render(<ActivateServiceButton />);
      expect(state.operationId).toBe(`partial_update_${resource}`);
      expect(activationButton("serviceShow.activate")).toBeInTheDocument();
      unmount();
    }
  });

  it("asks the api to activate the service of the record", async () => {
    state.record = { id: "wfs-1", isActive: false };
    render(<ActivateServiceButton />);
    fireEvent.click(activationButton("serviceShow.activate") as HTMLElement);
    expect(state.update).toHaveBeenCalledWith(
      "WebMapService",
      expect.objectContaining({
        id: "wfs-1",
        data: { isActive: true },
        previousData: state.record,
      }),
    );
    await waitFor(() =>
      expect(state.notify).toHaveBeenCalledWith("serviceShow.activated", {
        type: "success",
      }),
    );
    expect(state.refresh).toHaveBeenCalled();
  });

  it("asks the api to deactivate an active service", async () => {
    state.record = { id: "wfs-1", isActive: true };
    render(<ActivateServiceButton />);
    fireEvent.click(activationButton("serviceShow.deactivate") as HTMLElement);
    expect(state.update).toHaveBeenCalledWith(
      "WebMapService",
      expect.objectContaining({ data: { isActive: false } }),
    );
    await waitFor(() =>
      expect(state.notify).toHaveBeenCalledWith("serviceShow.deactivated", {
        type: "success",
      }),
    );
  });

  it("tells the user when the api refused the change", async () => {
    state.record = { id: "wfs-1", isActive: false };
    state.refused = true;
    render(<ActivateServiceButton />);
    fireEvent.click(activationButton("serviceShow.activate") as HTMLElement);
    await waitFor(() =>
      expect(state.notify).toHaveBeenCalledWith(
        "serviceShow.activationFailed",
        { type: "error" },
      ),
    );
    expect(state.refresh).not.toHaveBeenCalled();
  });

  it("disables submission while a request is pending", () => {
    state.record = { id: "wfs-1", isActive: false };
    state.isPending = true;
    render(<ActivateServiceButton />);
    expect(activationButton("serviceShow.activate")).toBeDisabled();
  });

  it("offers no action for a service which the api does not update", () => {
    state.record = { id: "wfs-1", isActive: false };
    state.updatable = false;
    render(<ActivateServiceButton />);
    expect(activationButton("serviceShow.activate")).toBeNull();
  });

  it("offers no action for a record which does not report its activation", () => {
    state.record = { id: "wfs-1" };
    render(<ActivateServiceButton />);
    expect(activationButton("serviceShow.activate")).toBeNull();
  });
});
