import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, type PropsWithChildren } from "react";
import {
  AdminContext,
  RecordContextProvider,
  testDataProvider,
} from "react-admin";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LivePreview from "./LivePreview";
import type { PreviewResult } from "./usePreview";

const state = vi.hoisted(() => ({
  request: vi.fn(),
  transfer: vi.fn(),
  reset: vi.fn(),
  mapProps: undefined as Record<string, unknown> | undefined,
}));
vi.mock("../../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "https://mrmap.test",
  useHttpClientContext: () => ({
    api: {
      getOperation: () => ({}),
      getAxiosConfigForOperation: (
        operation: string,
        [params, , options]: [
          Record<string, unknown>,
          unknown,
          Record<string, unknown>,
        ],
      ) => ({
        url: "https://mrmap.test/preview",
        operation,
        params,
        ...options,
      }),
      client: { request: state.request },
    },
  }),
}));
vi.mock("../../../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: "mrmap-token" }),
}));
vi.mock("../../../../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  OwsContextBase: ({ children }: PropsWithChildren) => (
    <div data-testid="isolated-context">{children}</div>
  ),
  useOwsContextBase: () => ({
    addWMSByUrl: state.transfer,
    resetContext: state.reset,
  }),
}));
vi.mock("./PreviewMap", () => ({
  validExtent: (extent?: number[]) => Boolean(extent),
  default: (props: {
    onViewport: (value: Record<string, unknown>) => void;
    image?: string;
    features?: object;
    records?: object[];
    identifyAvailable?: boolean;
    onIdentify?: (x: number, y: number) => void;
  }) => {
    state.mapProps = props;
    useEffect(() => {
      props.onViewport({ bbox: "0,0,4,8", width: 600, height: 400 });
    }, [props.onViewport]);
    return (
      <div data-testid="preview-map">
        {props.image && "live imagery"}
        {props.features && "live features"}
        {props.records && "metadata coverage"}
        {props.identifyAvailable && (
          <button onClick={() => props.onIdentify?.(300, 200)}>Identify</button>
        )}
      </div>
    );
  },
}));
const configuration = { extent: null, queryable: false };
const result = (data: Partial<PreviewResult>) => ({
  data: { source: "Registered service", ...data },
});
const prepare = (protocol: "WMS" | "WFS" | "CSW") => {
  const provider = testDataProvider({
    getList: vi.fn().mockResolvedValue({
      data: [{ id: "layer", identifier: "roads", title: "Roads" }],
      total: 1,
    }),
  });
  return render(
    <AdminContext
      dataProvider={provider}
      i18nProvider={{
        translate: (key) => key,
        changeLocale: async () => {},
        getLocale: () => "en",
      }}
    >
      <RecordContextProvider value={{ id: "service", title: "Service" }}>
        <LivePreview protocol={protocol} />
      </RecordContextProvider>
    </AdminContext>,
  );
};
beforeEach(() => {
  vi.clearAllMocks();
  state.mapProps = undefined;
});
afterEach(() => vi.unstubAllGlobals());
describe("live overview previews", () => {
  it("requests identify through the registered action and presents a safe result link", async () => {
    const BrowserURL = URL;
    vi.stubGlobal(
      "URL",
      class extends BrowserURL {
        static createObjectURL = vi.fn(() => "blob:safe-result");
        static revokeObjectURL = vi.fn();
      },
    );
    state.request.mockImplementation(async ({ params }) =>
      result(
        params.identify === "true"
          ? { info: "<script>remote</script>" }
          : params.bbox
            ? {
                image: "data:image/png;base64,test",
                configuration: { ...configuration, queryable: true },
              }
            : { configuration: { ...configuration, queryable: true } },
      ),
    );
    const view = prepare("WMS");
    fireEvent.click(screen.getByText("livePreview.title"));
    fireEvent.click(
      await screen.findByRole(
        "button",
        { name: "Identify" },
        { timeout: 3000 },
      ),
    );
    await screen.findByText("<script>remote</script>", {}, { timeout: 3000 });
    expect(
      screen.getByRole("link", { name: "livePreview.featureInfo" }),
    ).toHaveAttribute("href", "blob:safe-result");
    expect(document.querySelector("script")).toBeNull();
    expect(state.request).toHaveBeenCalledWith(
      expect.objectContaining({
        params: expect.objectContaining({ identify: "true", x: 300, y: 200 }),
      }),
    );
    view.unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:safe-result");
  });
  it("starts only on expansion, isolates state, and cancels when collapsed", async () => {
    state.request.mockImplementation(async ({ params }) =>
      result(
        params.bbox
          ? {
              image: "data:image/png;base64,test",
              fetchedAt: "2026-10-13T12:00:00Z",
              configuration,
            }
          : { configuration, discovery: "stored" },
      ),
    );
    prepare("WMS");
    expect(state.request).not.toHaveBeenCalled();
    expect(screen.queryByTestId("preview-map")).toBeNull();
    fireEvent.click(screen.getByText("livePreview.title"));
    expect(screen.getByTestId("isolated-context")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByLabelText("livePreview.layer"));
    fireEvent.click(await screen.findByRole("option", { name: "Roads" }));
    await screen.findByText("live imagery");
    expect(state.reset).not.toHaveBeenCalled();
    expect(state.transfer).not.toHaveBeenCalled();
    expect(state.request).toHaveBeenLastCalledWith(
      expect.objectContaining({
        headers: {
          Accept: "application/json",
          Authorization: "Token mrmap-token",
        },
        params: expect.objectContaining({
          selection: "roads",
          bbox: "0,0,4,8",
        }),
      }),
    );
    fireEvent.click(screen.getByText("livePreview.title"));
    await waitFor(() => expect(screen.queryByTestId("preview-map")).toBeNull());
  });
  it("shows actual bounded WFS features and visibility controls", async () => {
    state.request.mockImplementation(async ({ params }) =>
      result(
        params.bbox
          ? {
              features: { type: "FeatureCollection", features: [] },
              limited: true,
              limit: 500,
              fetchedAt: "2026-10-13T12:00:00Z",
              configuration,
            }
          : { configuration },
      ),
    );
    prepare("WFS");
    fireEvent.click(screen.getByText("livePreview.title"));
    fireEvent.mouseDown(screen.getByLabelText("livePreview.featureType"));
    fireEvent.click(await screen.findByRole("option", { name: "Roads" }));
    await screen.findByText("live features");
    expect(screen.getByText("livePreview.limited")).toBeInTheDocument();
    expect(screen.getByText("livePreview.emptyFeatures")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("livePreview.visible"));
    expect(screen.queryByText("live features")).toBeNull();
  });
  it("shows a retryable failure without replacing stored overview content", async () => {
    state.request.mockRejectedValue({
      response: { status: 422, data: { error: "format" } },
    });
    prepare("WFS");
    fireEvent.click(screen.getByText("livePreview.title"));
    fireEvent.mouseDown(screen.getByLabelText("livePreview.featureType"));
    fireEvent.click(await screen.findByRole("option", { name: "Roads" }));
    await screen.findByText("livePreview.errors.format");
    expect(
      screen.getByRole("button", { name: "ra.action.retry" }),
    ).toBeInTheDocument();
    expect(screen.getByText("livePreview.storedDiscovery")).toBeInTheDocument();
  });
  it("queries fresh CSW pages, labels metadata coverage, and retains records without links/extents", async () => {
    state.request.mockImplementation(async ({ params }) =>
      result({
        records: [
          {
            identifier: "record",
            title: "Live record",
            abstract: "<script>remote</script>",
            extent: null,
            previews: [],
          },
        ],
        next: params.start === 1 ? 26 : 0,
        matched: 26,
        fetchedAt: "2026-10-13T12:00:00Z",
      }),
    );
    prepare("CSW");
    fireEvent.click(screen.getByText("livePreview.title"));
    await screen.findByText("livePreview.noRegistered");
    expect(screen.getByText("livePreview.noCoverage")).toBeInTheDocument();
    expect(screen.getByText("<script>remote</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText("metadata coverage")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "ra.navigation.next" }));
    await waitFor(() =>
      expect(state.request).toHaveBeenLastCalledWith(
        expect.objectContaining({ params: { id: "service", start: 26 } }),
      ),
    );
    expect(
      screen.getByRole("button", { name: "ra.navigation.previous" }),
    ).toBeEnabled();
  });
  it("offers only verified registered CSW links", async () => {
    state.request.mockResolvedValue(
      result({
        records: [
          {
            identifier: "record",
            title: "Linked record",
            extent: [0, 0, 4, 8],
            previews: [
              {
                protocol: "WFS",
                serviceId: "verified",
                selection: "roads",
                title: "Roads",
              },
            ],
          },
        ],
        matched: 1,
        next: 0,
      }),
    );
    prepare("CSW");
    fireEvent.click(screen.getByText("livePreview.title"));
    fireEvent.click(
      await screen.findByRole("button", { name: "livePreview.previewLinked" }),
    );
    await waitFor(() =>
      expect(state.request).toHaveBeenCalledWith(
        expect.objectContaining({
          operation: "preview_WebFeatureService",
          params: expect.objectContaining({
            id: "verified",
            selection: "roads",
          }),
        }),
      ),
    );
  });
});
