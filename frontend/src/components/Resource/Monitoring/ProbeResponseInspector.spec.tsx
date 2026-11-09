import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProbeResponseInspector, {
  type ProbeExecution,
} from "./ProbeResponseInspector";

const state = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("../../../context/HttpClientContext", () => ({
  API_BASE_URL: "https://mrmap.test",
  useHttpClientContext: () => ({ api: { client: { request: state.request } } }),
}));
vi.mock("../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: "mrmap-token" }),
}));
vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
}));

const execution = (overrides: Partial<ProbeExecution>): ProbeExecution => ({
  statusCode: 200,
  monitoredUri: "https://example.de/wms?REQUEST=GetMap",
  requestDuration: "0:00:01.234567",
  responseSize: 4321,
  responseContentType: "image/png",
  hasResponseArtifact: true,
  responseArtifactUrl:
    "/api/registry/monitoring/probe-results/getmapproberesult/7/response",
  ...overrides,
});

const renderInspector = (value: ProbeExecution) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProbeResponseInspector execution={value} />
    </QueryClientProvider>,
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  const BrowserURL = URL;
  vi.stubGlobal(
    "URL",
    class extends BrowserURL {
      static createObjectURL = vi.fn(() => "blob:probe-response");
      static revokeObjectURL = vi.fn();
    },
  );
});

describe("probe response inspector", () => {
  it("answers the summary of the request without any body", () => {
    renderInspector(
      execution({
        hasResponseArtifact: false,
        responseArtifactUrl: null,
        responseContentType: "text/html",
      }),
    );

    expect(screen.getByText("monitoringRun.response.title")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("1.2 s")).toBeInTheDocument();
    expect(screen.getByText("4 KB")).toBeInTheDocument();
    // the uri reaches the card already redacted by the backend answer
    expect(
      screen.getByText("https://example.de/wms?REQUEST=GetMap"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("monitoringRun.response.notStored"),
    ).toBeInTheDocument();
    expect(state.request).not.toHaveBeenCalled();
  });

  it("names the request error when the service never answered", () => {
    renderInspector(
      execution({
        statusCode: null,
        requestError: "ConnectTimeout: connect timed out",
        errorDetail: "after 10 seconds",
        hasResponseArtifact: false,
        responseArtifactUrl: null,
        responseSize: null,
        responseContentType: "",
      }),
    );

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("ConnectTimeout: connect timed out");
    expect(alert).toHaveTextContent("after 10 seconds");
    expect(screen.queryByText("monitoringRun.response.status")).not.toBeInTheDocument();
  });

  it("fetches a stored image with authentication and shows it", async () => {
    const blob = new Blob(["png"], { type: "image/png" });
    state.request.mockResolvedValue({ data: blob });
    renderInspector(execution({}));

    const image = await screen.findByAltText("monitoringRun.response.image");
    expect(image).toHaveAttribute("src", "blob:probe-response");
    expect(state.request).toHaveBeenCalledWith({
      url: "https://mrmap.test/api/registry/monitoring/probe-results/getmapproberesult/7/response",
      responseType: "blob",
      signal: expect.any(AbortSignal),
      headers: { Accept: "*/*", Authorization: "Token mrmap-token" },
    });
  });

  it("renders a stored OGC exception as readable text", async () => {
    const body =
      '<?xml version="1.0"?><ServiceExceptionReport><ServiceException code="LayerNotDefined">no such layer</ServiceException></ServiceExceptionReport>';
    state.request.mockResolvedValue({
      data: new Blob([body], { type: "application/xml" }),
    });
    renderInspector(
      execution({ responseContentType: "application/xml" }),
    );

    const document = await screen.findByText(/LayerNotDefined/);
    expect(document.tagName).toBe("PRE");
    expect(
      screen.getByText("monitoringRun.response.download"),
    ).toBeInTheDocument();
  });

  it.each([
    { status: 410, message: "monitoringRun.response.expired" },
    { status: 404, message: "monitoringRun.response.missing" },
    { status: 403, message: "monitoringRun.response.unavailable" },
  ])("answers a gone or refused body (%i) gracefully", async ({ status, message }) => {
    state.request.mockRejectedValue({ response: { status } });
    renderInspector(execution({}));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("never requests a body the endpoint would only attach", async () => {
    renderInspector(
      execution({
        responseContentType: "application/octet-stream",
      }),
    );

    expect(
      await screen.findByText(/monitoringRun.response.notRenderable/),
    ).toBeInTheDocument();
    expect(state.request).not.toHaveBeenCalled();
  });

  it("rejects an artifact URL outside the MrMap API", async () => {
    renderInspector(
      execution({
        responseArtifactUrl: "https://upstream.test/response.png",
      }),
    );

    expect(
      await screen.findByText("monitoringRun.response.unavailable"),
    ).toBeInTheDocument();
    expect(state.request).not.toHaveBeenCalled();
  });

  it("revokes the object URL when the card goes away", async () => {
    state.request.mockResolvedValue({
      data: new Blob(["png"], { type: "image/png" }),
    });
    const view = renderInspector(execution({}));
    await screen.findByAltText("monitoringRun.response.image");

    view.unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:probe-response");
  });
});
