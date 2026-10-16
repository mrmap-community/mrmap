import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MapViewerButton from "./MapViewerButton";

const state = vi.hoisted(() => ({
  record: { id: "service" } as Record<string, unknown>,
  query: {
    data: undefined as Record<string, unknown> | undefined,
    isLoading: false,
  },
  context: { features: [] as object[] },
  refetch: vi.fn(),
  addWMSByUrl: vi.fn(),
  resetContext: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock("react-admin", () => ({
  Button: ({
    label,
    onClick,
    disabled,
    children,
  }: {
    label: string;
    onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
    disabled: boolean;
    children: ReactNode;
  }) => (
    <button disabled={disabled} onClick={onClick}>
      {children}
      {label}
    </button>
  ),
  useGetOne: () => ({ ...state.query, refetch: state.refetch }),
  useRecordContext: () => state.record,
  useTranslate: () => (key: string) => key,
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => state.navigate,
}));
vi.mock("../../../../providers/authProvider", () => ({
  getAuthToken: () => undefined,
}));
vi.mock("../../../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  useOwsContextBase: () => ({
    owsContext: state.context,
    addWMSByUrl: state.addWMSByUrl,
    resetContext: state.resetContext,
  }),
}));

const operationUrls = [
  { operation: 1, method: 1, url: "https://wms.example.test/ows" },
];
const service = {
  id: "service",
  operationUrls,
  layers: [{ id: "layer", identifier: "roads", isActive: true }],
};

beforeEach(() => {
  vi.clearAllMocks();
  state.record = { id: "service", operationUrls };
  state.query.data = undefined;
  state.query.isLoading = false;
  state.context = { features: [] };
});

describe("map viewer button", () => {
  it("keeps service fetching and the viewer idle until clicked", () => {
    render(<MapViewerButton />);

    expect(state.refetch).not.toHaveBeenCalled();
    expect(state.resetContext).not.toHaveBeenCalled();
    expect(state.addWMSByUrl).not.toHaveBeenCalled();
    expect(state.navigate).not.toHaveBeenCalled();
  });

  it("waits for service details before opening a known capabilities URL", () => {
    const view = render(<MapViewerButton />);
    fireEvent.click(screen.getByRole("button"));

    expect(state.refetch).toHaveBeenCalledOnce();
    expect(state.resetContext).not.toHaveBeenCalled();
    expect(state.addWMSByUrl).not.toHaveBeenCalled();
    expect(state.navigate).not.toHaveBeenCalled();

    state.query.data = service;
    view.rerender(<MapViewerButton />);

    expect(state.refetch).toHaveBeenCalledOnce();
    expect(state.resetContext).toHaveBeenCalledOnce();
    expect(state.addWMSByUrl).toHaveBeenCalledOnce();
    expect(state.navigate).toHaveBeenCalledWith("/viewer");
    const url = new URL(state.addWMSByUrl.mock.calls[0][0]);
    expect(url.searchParams.get("REQUEST")).toBe("GetCapabilities");

    const operation = { href: "https://wms.example.test/ows?LAYERS=roads" };
    const context = {
      features: [
        {
          properties: { folder: "/1/roads" },
          getWmsOperationByCode: () => operation,
        },
      ],
    };
    state.addWMSByUrl.mock.calls[0][2](context, 1);
    expect(operation).toEqual(
      expect.objectContaining({
        "x-mrmap-service-id": "service",
        "x-mrmap-layer-id": "layer",
        "x-mrmap-layer-properties": service.layers[0],
      }),
    );
  });

  it("opens after the requested service supplies its capabilities URL", () => {
    state.record = { id: "service" };
    const view = render(<MapViewerButton />);
    fireEvent.click(screen.getByRole("button"));

    expect(state.refetch).toHaveBeenCalledOnce();
    expect(state.addWMSByUrl).not.toHaveBeenCalled();

    state.query.data = service;
    view.rerender(<MapViewerButton />);

    expect(state.refetch).toHaveBeenCalledOnce();
    expect(state.addWMSByUrl).toHaveBeenCalledOnce();
    expect(state.navigate).toHaveBeenCalledWith("/viewer");
  });

  it("waits for the existing map context to clear before adding the service", () => {
    state.context = { features: [{}] };
    const view = render(<MapViewerButton />);
    fireEvent.click(screen.getByRole("button"));

    state.query.data = service;
    view.rerender(<MapViewerButton />);

    expect(state.resetContext).toHaveBeenCalledOnce();
    expect(state.addWMSByUrl).not.toHaveBeenCalled();
    expect(state.navigate).not.toHaveBeenCalled();

    state.context = { features: [] };
    view.rerender(<MapViewerButton />);

    expect(state.addWMSByUrl).toHaveBeenCalledOnce();
    expect(state.navigate).toHaveBeenCalledWith("/viewer");
  });
});
