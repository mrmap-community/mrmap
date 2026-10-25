import type { ReactNode } from "react";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WfsMapViewerButton from "./MapViewerButton";

const state = vi.hoisted(() => ({
  record: { id: "service" } as Record<string, unknown>,
  query: {
    data: undefined as Record<string, unknown> | undefined,
    isLoading: false,
  },
  context: { features: [] as object[] },
  refetch: vi.fn(),
  addWFSByUrl: vi.fn(),
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
    onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void;
    disabled?: boolean;
    children?: ReactNode;
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
    addWFSByUrl: state.addWFSByUrl,
    resetContext: state.resetContext,
  }),
}));

const operationUrls = [
  { operation: 1, method: 1, url: "https://wfs.example.test/ows" },
];
const featuretypes = [
  { id: "ft1", identifier: "roads", title: "Roads" },
  { id: "ft2", identifier: "rivers", title: "Rivers" },
];
const service = { id: "service", title: "WFS", operationUrls, featuretypes };

/** a context shaped like the appended WFS tree, for inspecting the beforeSetHook */
const wfsContext = () =>
  ["roads", "rivers"].map((identifier) => {
    const operation: Record<string, unknown> = {
      href: `https://wfs.example.test/ows?TYPENAME=${identifier}`,
    };
    const properties: Record<string, unknown> = { folder: `/1/${identifier}` };
    return {
      properties,
      getWfsOffering: () => ({}),
      getWfsOperationByCode: () => operation,
      operation,
    };
  });

beforeEach(() => {
  vi.clearAllMocks();
  state.record = { id: "service", operationUrls };
  state.query.data = undefined;
  state.query.isLoading = false;
  state.context = { features: [] };
});

const clickAndLoad = () => {
  const view = render(<WfsMapViewerButton />);
  fireEvent.click(screen.getByRole("button", { name: "ra.action.mapviewer" }));
  expect(state.refetch).toHaveBeenCalledOnce();
  state.query.data = service;
  view.rerender(<WfsMapViewerButton />);
  return view;
};

describe("wfs map viewer button", () => {
  it("keeps service fetching and the viewer idle until clicked", () => {
    render(<WfsMapViewerButton />);

    expect(state.refetch).not.toHaveBeenCalled();
    expect(state.resetContext).not.toHaveBeenCalled();
    expect(state.addWFSByUrl).not.toHaveBeenCalled();
    expect(state.navigate).not.toHaveBeenCalled();
  });

  it("asks which feature types the viewer shall show and hands the chosen ones over", () => {
    clickAndLoad();

    // the schema-driven related list answers the selection, all types preselected
    expect(screen.getByText("Roads (roads)")).toBeInTheDocument();
    expect(screen.getByText("Rivers (rivers)")).toBeInTheDocument();

    fireEvent.click(screen.getByText("ra.action.add"));

    expect(state.resetContext).toHaveBeenCalledOnce();
    expect(state.addWFSByUrl).toHaveBeenCalledOnce();
    expect(state.navigate).toHaveBeenCalledWith("/viewer");
    const url = new URL(state.addWFSByUrl.mock.calls[0][0]);
    expect(url.searchParams.get("SERVICE")).toBe("wfs");
    expect(url.searchParams.get("REQUEST")).toBe("GetCapabilities");

    const features = wfsContext();
    const hook = state.addWFSByUrl.mock.calls[0][2];
    hook({ features });
    for (const feature of features) {
      expect(feature.operation).toEqual(
        expect.objectContaining({ "x-mrmap-service-id": "service" }),
      );
      expect(feature.properties.active).toBe(true);
    }
    const roads = features.find((feature) =>
      String(feature.operation.href).includes("roads"))!;
    expect(roads.operation["x-mrmap-feature-type-id"]).toBe("ft1");
    expect(roads.operation["x-mrmap-feature-type-properties"]).toEqual(
      featuretypes[0],
    );
  });

  it("keeps the types the user deselected inactive", () => {
    clickAndLoad();

    fireEvent.click(screen.getByText("Rivers (rivers)"));
    fireEvent.click(screen.getByText("ra.action.add"));

    const features = wfsContext();
    state.addWFSByUrl.mock.calls[0][2]({ features });
    const roads = features.find((feature) =>
      String(feature.operation.href).includes("roads"))!;
    const rivers = features.find((feature) =>
      String(feature.operation.href).includes("rivers"))!;
    expect(roads.properties.active).toBe(true);
    expect(rivers.properties.active).toBe(false);
  });

  it("activates a type the service announces qualified with a namespace prefix", () => {
    const view = render(<WfsMapViewerButton />);
    fireEvent.click(screen.getByRole("button", { name: "ra.action.mapviewer" }));
    // the database stores the local part, while the capabilities qualify the name (ms:Countries)
    state.query.data = {
      ...service,
      featuretypes: [{ id: "ft1", identifier: "countries", title: "Countries" }],
    };
    view.rerender(<WfsMapViewerButton />);

    expect(screen.getByText("Countries (countries)")).toBeInTheDocument();
    fireEvent.click(screen.getByText("ra.action.add"));

    const operation: Record<string, unknown> = {
      href: "https://wfs.example.test/ows?TYPENAME=ms%3ACountries",
    };
    const feature = {
      properties: { folder: "/1/0" } as Record<string, unknown>,
      getWfsOffering: () => ({}),
      getWfsOperationByCode: () => operation,
    };
    state.addWFSByUrl.mock.calls[0][2]({ features: [feature] });

    expect(feature.properties.active).toBe(true);
    expect(operation.active).toBe(true);
    expect(operation["x-mrmap-feature-type-id"]).toBe("ft1");
    expect(operation["x-mrmap-feature-type-properties"]).toEqual({
      id: "ft1",
      identifier: "countries",
      title: "Countries",
    });
  });

  it("waits for the existing map context to clear before adding the service", () => {
    state.context = { features: [{}] };
    const view = clickAndLoad();

    fireEvent.click(screen.getByText("ra.action.add"));

    expect(state.resetContext).toHaveBeenCalledOnce();
    expect(state.addWFSByUrl).not.toHaveBeenCalled();
    expect(state.navigate).not.toHaveBeenCalled();

    state.context = { features: [] };
    view.rerender(<WfsMapViewerButton />);

    expect(state.addWFSByUrl).toHaveBeenCalledOnce();
    expect(state.navigate).toHaveBeenCalledWith("/viewer");
  });
});
