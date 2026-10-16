import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { useRecordContext } from "react-admin";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ServicePreviewImage from "./ServicePreviewImage";

const state = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock("../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "https://mrmap.test",
  useHttpClientContext: () => ({ api: { client: { request: state.request } } }),
}));
vi.mock("../../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: "mrmap-token" }),
}));
vi.mock("react-admin", () => ({
  useRecordContext: vi.fn(),
  useTranslate: () => (key: string, options?: { title?: string }) =>
    key === "serviceShow.preview" ? `Preview of ${options?.title}` : key,
}));

const record = {
  id: "wms-1",
  title: "Service",
  previewUrl: "https://example.com/wms?REQUEST=GetMap&LAYERS=roads,buildings",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useRecordContext).mockReturnValue(record);
});
afterEach(() => vi.unstubAllGlobals());

describe("service preview image", () => {
  it("loads the backend URL immediately and replaces the loading placeholder on success", () => {
    render(<ServicePreviewImage />);
    const image = screen.getByAltText("Preview of Service");
    expect(image).toHaveAttribute("src", record.previewUrl);
    expect(
      screen.getByRole("status", { name: "serviceShow.previewLoading" }),
    ).toBeInTheDocument();

    fireEvent.load(image);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(image).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each([undefined, null, "", "   "])(
    "shows an unavailable placeholder for a missing URL (%s)",
    (previewUrl) => {
      vi.mocked(useRecordContext).mockReturnValue({ ...record, previewUrl });
      render(<ServicePreviewImage />);

      expect(screen.queryByRole("img")).not.toBeInTheDocument();
      expect(screen.getByRole("status")).toHaveTextContent(
        "serviceShow.previewUnavailable",
      );
    },
  );

  it("replaces a failed image with the unavailable placeholder", () => {
    render(<ServicePreviewImage />);
    fireEvent.error(screen.getByAltText("Preview of Service"));

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "serviceShow.previewUnavailable",
    );
  });

  it.each([
    { ...record, id: "wms-2" },
    { ...record, previewUrl: "https://example.com/updated-preview.png" },
  ])("loads again after the service or URL changes", (nextRecord) => {
    const view = render(<ServicePreviewImage />);
    fireEvent.error(screen.getByAltText("Preview of Service"));

    vi.mocked(useRecordContext).mockReturnValue(nextRecord);
    view.rerender(<ServicePreviewImage />);

    expect(screen.getByAltText("Preview of Service")).toHaveAttribute(
      "src",
      nextRecord.previewUrl,
    );
    expect(
      screen.getByRole("status", { name: "serviceShow.previewLoading" }),
    ).toBeInTheDocument();
    fireEvent.load(screen.getByAltText("Preview of Service"));
    expect(screen.getByRole("img")).toBeVisible();
  });

  it("waits for a service record", () => {
    vi.mocked(useRecordContext).mockReturnValue(undefined);
    const { container } = render(<ServicePreviewImage />);

    expect(container).toBeEmptyDOMElement();
  });
});

const wfsRecord = {
  ...record,
  id: "wfs-1",
  previewUrl: "/api/registry/wfs/wfs-1/preview-image/",
};
const renderAuthenticated = () => {
  const client = new QueryClient();
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<ServicePreviewImage authenticated />, { wrapper });
};

describe("authenticated service preview image", () => {
  beforeEach(() => {
    vi.mocked(useRecordContext).mockReturnValue(wfsRecord);
    const BrowserURL = URL;
    vi.stubGlobal(
      "URL",
      class extends BrowserURL {
        static createObjectURL = vi.fn(() => "blob:wfs-preview");
        static revokeObjectURL = vi.fn();
      },
    );
  });

  it("fetches the API image with authentication and shows the blob thumbnail", async () => {
    const imageBlob = new Blob(["png"], { type: "image/png" });
    state.request.mockResolvedValue({ data: imageBlob });
    renderAuthenticated();

    expect(
      screen.getByRole("status", { name: "serviceShow.previewLoading" }),
    ).toBeInTheDocument();
    const image = await screen.findByAltText("Preview of Service");
    expect(image).toHaveAttribute("src", "blob:wfs-preview");
    expect(URL.createObjectURL).toHaveBeenCalledWith(imageBlob);
    expect(state.request).toHaveBeenCalledWith({
      url: `https://mrmap.test${wfsRecord.previewUrl}`,
      responseType: "blob",
      signal: expect.any(AbortSignal),
      headers: { Accept: "image/png", Authorization: "Token mrmap-token" },
    });
    fireEvent.load(image);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(image).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it.each(["network", "non-image"])(
    "shows an unavailable placeholder for a %s response",
    async (failure) => {
      if (failure === "network")
        state.request.mockRejectedValue(new Error("HTTP 403"));
      else
        state.request.mockResolvedValue({
          data: new Blob(["{}"], { type: "application/json" }),
        });
      renderAuthenticated();

      expect(
        await screen.findByText("serviceShow.previewUnavailable"),
      ).toBeInTheDocument();
      expect(screen.queryByRole("img")).not.toBeInTheDocument();
      expect(URL.createObjectURL).not.toHaveBeenCalled();
    },
  );

  it("rejects an upstream URL before attaching MrMap authentication", async () => {
    vi.mocked(useRecordContext).mockReturnValue({
      ...wfsRecord,
      previewUrl: "https://upstream.test/wfs",
    });
    renderAuthenticated();

    expect(
      await screen.findByText("serviceShow.previewUnavailable"),
    ).toBeInTheDocument();
    expect(state.request).not.toHaveBeenCalled();
  });

  it("does not request an image when the preview URL is missing", () => {
    vi.mocked(useRecordContext).mockReturnValue({
      ...wfsRecord,
      previewUrl: "",
    });
    renderAuthenticated();

    expect(screen.getByRole("status")).toHaveTextContent(
      "serviceShow.previewUnavailable",
    );
    expect(state.request).not.toHaveBeenCalled();
  });

  it("revokes blob URLs when the service changes and on unmount", async () => {
    state.request.mockResolvedValue({
      data: new Blob(["png"], { type: "image/png" }),
    });
    vi.mocked(URL.createObjectURL)
      .mockReturnValueOnce("blob:first-preview")
      .mockReturnValueOnce("blob:second-preview");
    const view = renderAuthenticated();
    expect(await screen.findByAltText("Preview of Service")).toHaveAttribute(
      "src",
      "blob:first-preview",
    );
    vi.mocked(useRecordContext).mockReturnValue({
      ...wfsRecord,
      id: "wfs-2",
      previewUrl: "/api/registry/wfs/wfs-2/preview-image/",
    });
    view.rerender(<ServicePreviewImage authenticated />);

    await waitFor(() =>
      expect(screen.getByAltText("Preview of Service")).toHaveAttribute(
        "src",
        "blob:second-preview",
      ),
    );
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:first-preview");
    view.unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:second-preview");
  });

  it("cancels an unfinished request on unmount", async () => {
    state.request.mockReturnValue(new Promise(() => {}));
    const view = renderAuthenticated();
    await waitFor(() => expect(state.request).toHaveBeenCalledOnce());
    const signal = state.request.mock.calls[0][0].signal as AbortSignal;
    view.unmount();

    expect(signal.aborted).toBe(true);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
