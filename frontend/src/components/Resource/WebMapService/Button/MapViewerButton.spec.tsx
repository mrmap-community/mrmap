import type { ReactNode } from "react";

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OWSContext } from "../../../../ows-lib/OwsContext/core";
import inherited from "../../../../ows-lib/XMLParser/tests/capabilities_inherited_130.xml?raw";
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
  addWFSByUrl: vi.fn(),
  getOne: vi.fn(),
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
  useGetOne: (resource: string, params: unknown) => {
    state.getOne(resource, params);
    return { ...state.query, refetch: state.refetch };
  },
  useRecordContext: () => state.record,
  useTranslate: () => (key: string) => key,
}));
vi.mock("react-router-dom", () => ({
  useNavigate: () => state.navigate,
}));
vi.mock("../../../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  useOwsContextBase: () => ({
    owsContext: state.context,
    addWMSByUrl: state.addWMSByUrl,
    addWFSByUrl: state.addWFSByUrl,
    resetContext: state.resetContext,
  }),
}));
vi.mock('../../../../context/HttpClientContext', () => ({ API_BASE_URL: 'https://mrmap.example.test' }));

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
  it("loads a registered WFS through the proxy and opens it in the viewer", () => {
    const featureType = { id: 'feature-type', identifier: 'demo:roads' };
    state.query.data = { id: 'wfs-service', featuretypes: [featureType] };
    state.record = { id: 'wfs-service' };
    render(<MapViewerButton protocol="WFS" />);
    expect(state.addWFSByUrl).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button'));
    expect(state.getOne).toHaveBeenCalledWith('WebFeatureService', expect.objectContaining({
      id: 'wfs-service',
      meta: { jsonApiParams: expect.objectContaining({ include: 'featuretypes' }) },
    }));
    expect(state.resetContext).toHaveBeenCalledOnce();
    expect(state.addWMSByUrl).not.toHaveBeenCalled();
    expect(state.addWFSByUrl).toHaveBeenCalledOnce();
    const url = new URL(state.addWFSByUrl.mock.calls[0][0]);
    expect(url.origin).toBe('https://mrmap.example.test');
    expect(url.pathname).toBe('/mrmap-proxy/wfs/wfs-service');
    expect(url.searchParams.get('SERVICE')).toBe('WFS');
    expect(url.searchParams.get('VERSION')).toBe('2.0.0');
    // no header argument (#835): the viewer's request to this origin carries
    // the browser session's cookie by itself
    expect(state.addWFSByUrl.mock.calls[0][1]).toBeUndefined();
    const operation = { href: 'https://mrmap.example.test/mrmap-proxy/wfs/wfs-service?TYPENAME=demo:roads' };
    const context = {
      features: [{ properties: { folder: '/1/roads' }, getWfsOperationByCode: () => operation }],
    };
    state.addWFSByUrl.mock.calls[0][2](context, 1);
    expect(operation).toEqual(expect.objectContaining({
      'x-mrmap-service-id': 'wfs-service',
      'x-mrmap-featuretype-id': 'feature-type',
    }));
    expect(state.navigate).toHaveBeenCalledWith('/viewer');
  });
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

  it("opens the capabilities document of exactly one resource which is given", () => {
    state.query.data = service;
    render(
      <MapViewerButton capabilititesUrl="https://mrmap.example.test/mrmap-proxy/wms/service/layer/layer" />,
    );
    fireEvent.click(screen.getByRole("button"));

    expect(state.addWMSByUrl).toHaveBeenCalledOnce();
    const url = new URL(state.addWMSByUrl.mock.calls[0][0]);
    expect(url.pathname).toBe("/mrmap-proxy/wms/service/layer/layer");
    expect(url.searchParams.get("SERVICE")).toBe("WMS");
    expect(url.searchParams.get("REQUEST")).toBe("GetCapabilities");
    expect(state.navigate).toHaveBeenCalledWith("/viewer");
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

  // the tree of the viewer keeps the activation of a layer in its GetMap operation and the map draws
  // only what that operation marks active, so a button which is asked for one element of the
  // document has to tick it the way a click on the checkbox of the tree does - against a real
  // document, because both the layer lookup and the tree of a document decide here
  describe("beside a document it appends", () => {
    const capabilitiesUrl = "https://wms.example.test/ows?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities";
    // the records the registry stores for the layers the fixture advertises
    const fixtureLayers = [
      { id: "inheriting", identifier: "tests:inheriting", isActive: true },
      { id: "nested", identifier: "tests:nested", isActive: true },
    ];

    /** opens the viewer for one element and reports what the appended document ends up asking for */
    const openWith = (element: { id: string }) => {
      state.query.data = { ...service, layers: fixtureLayers };
      const view = render(<MapViewerButton element={element} />);
      fireEvent.click(screen.getByRole("button"));
      view.rerender(<MapViewerButton element={element} />);

      const context = new OWSContext();
      const treeId = context.appendWms(capabilitiesUrl, inherited);
      state.addWMSByUrl.mock.calls.at(-1)![2](context, treeId);
      view.unmount();

      const drawn = context.features.filter(
        feature => feature.getWmsOperationByCode("GetMap")?.active === true);
      return {
        drawn: drawn.map(feature => feature.properties.title),
        active: context.getActiveFeatures().map(feature => feature.properties.title),
        layerId: drawn.at(-1)?.getWmsOperationByCode("GetMap")?.["x-mrmap-layer-id"],
      };
    };

    it("ticks the layer it is asked to show and keeps the rest of the document inactive", () => {
      expect(openWith({ id: "nested" })).toEqual({
        // the group of the layer is inactive as a layer of its own: it has no GetMap to draw
        drawn: ["Nested layer"],
        active: ["Unnamed group", "Nested layer"],
        layerId: "nested",
      });
    });

    it("asks nothing of a document which does not hold the element", () => {
      expect(openWith({ id: "another" })).toEqual({ drawn: [], active: [], layerId: undefined });
    });
  });

  it("hands the proxy service over without any credential (#835)", () => {
    state.query.data = service;
    const proxyUrl = "https://mrmap.example.test/mrmap-proxy/wms/service";
    render(<MapViewerButton capabilititesUrl={proxyUrl} />);
    fireEvent.click(screen.getByRole("button"));

    // the operations as the freshly parsed document holds them: since #835 the
    // button passes no headers to the viewer, so the placeholder mechanism of
    // `assignServiceAuthentication` never marks this tree at all
    const proxyOperation: Record<string, unknown> = { href: proxyUrl };
    const upstreamOperation: Record<string, unknown> = {
      href: "https://upstream.example/ows?LAYERS=roads",
    };
    const context = {
      features: [
        {
          properties: { folder: "/1", offerings: [{ operations: [proxyOperation] }] },
          getWmsOperationByCode: () => proxyOperation,
        },
        {
          properties: { folder: "/1/roads", offerings: [{ operations: [upstreamOperation] }] },
          getWmsOperationByCode: () => upstreamOperation,
        },
      ],
    };
    state.addWMSByUrl.mock.calls[0][2](context, 1);

    // nothing hands a credential to the viewer any more: the proxy operation is
    // asked with the session cookie the browser attaches itself, and an
    // operation of another origin gets no credential from us at all - so no
    // operation carries an authentication id and no header is registered
    expect(state.addWMSByUrl.mock.calls[0][1]).toBeUndefined();
    expect(proxyOperation).not.toHaveProperty("x-authentication-id");
    expect(upstreamOperation).not.toHaveProperty("x-authentication-id");
    // the identity markers the proxy reads are not credentials and stay
    expect(proxyOperation).toHaveProperty("x-mrmap-service-id");
    expect(
      (context as unknown as { authenticationHeaders?: unknown[] })
        .authenticationHeaders,
    ).toBeUndefined();
  });
});
