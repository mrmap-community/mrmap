import type { ServiceProtocol } from "./ServiceDetailsCard";

import type { ComponentProps } from "react";
import {
  AdminContext,
  RecordContextProvider,
  ResourceContextProvider,
  TextField,
} from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ServiceOverview from "./ServiceOverview";

vi.mock("../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "https://mrmap.test",
  useHttpClientContext: () => ({
    api: {
      client: { request: () => new Promise(() => {}) },
      getOperation: () => ({}),
    },
  }),
}));
vi.mock("../../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: "mrmap-token" }),
}));
vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: () =>
    ["id", "title", "abstract", "version"].map((source) => ({
      component: TextField,
      props: { source },
    })),
}));
vi.mock("./ServiceHistoryCard", () => ({
  default: () => <div>Service history</div>,
}));
vi.mock("./LivePreview/LivePreview", () => ({
  default: ({ protocol }: { protocol: string }) => (
    <div>Live preview {protocol}</div>
  ),
}));
vi.mock("../../WebMapService/Button/MapViewerButton", () => ({
  default: ({ label }: { label: string }) => <button>{label}</button>,
}));

const service = {
  id: "service-1",
  title: "Example service",
  abstract: "Service description",
  isActive: false,
  previewUrl: "https://example.com/preview.png",
  operationUrls: [
    { id: "url-1", operation: 1, method: 1, url: "https://example.com/wms" },
  ],
};

const setup = (
  protocol: ServiceProtocol,
  record = service,
  props: Partial<ComponentProps<typeof ServiceOverview>> = {},
) =>
  render(
    <AdminContext
      i18nProvider={{
        translate: (key) => key,
        changeLocale: async () => {},
        getLocale: () => "en",
      }}
    >
      <ResourceContextProvider
        value={
          {
            WMS: "WebMapService",
            WFS: "WebFeatureService",
            CSW: "CatalogueService",
          }[protocol]
        }
      >
        <RecordContextProvider value={record}>
          <ServiceOverview protocol={protocol} {...props} />
        </RecordContextProvider>
      </ResourceContextProvider>
    </AdminContext>,
  );

describe("service overview previews", () => {
  it("shows the WMS thumbnail and viewer action inside service details without a live preview", () => {
    setup("WMS");

    expect(screen.getByAltText("serviceShow.preview")).toHaveAttribute(
      "src",
      service.previewUrl,
    );
    expect(screen.getByText(service.title)).toBeInTheDocument();
    expect(screen.getByText(service.abstract)).toBeInTheDocument();
    expect(screen.getByText(service.id)).toBeInTheDocument();
    expect(screen.getByText("Service history")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "serviceShow.openMapViewer" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "serviceShow.activate" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Live preview WMS")).not.toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      expect.stringContaining("REQUEST=GetCapabilities"),
    );
  });

  it("keeps the service information and viewer action available when the preview is missing", () => {
    setup("WMS", { ...service, previewUrl: "" });

    expect(
      screen.getByText("serviceShow.previewUnavailable"),
    ).toBeInTheDocument();
    expect(screen.getByText(service.title)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "serviceShow.openMapViewer" }),
    ).toBeInTheDocument();
  });

  it("loads the WFS thumbnail in service details without a live preview or viewer action", () => {
    setup("WFS", {
      ...service,
      previewUrl: "/api/registry/wfs/service-1/preview-image/",
    });

    expect(
      screen.getByRole("status", { name: "serviceShow.previewLoading" }),
    ).toBeInTheDocument();
    expect(screen.getByText(service.title)).toBeInTheDocument();
    expect(screen.queryByText("Live preview WFS")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "serviceShow.activate" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "serviceShow.openMapViewer" }),
    ).not.toBeInTheDocument();
  });

  it("preserves the CSW live preview without a thumbnail or viewer action", () => {
    setup("CSW");

    expect(screen.getByText("Live preview CSW")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "serviceShow.activate" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByAltText("serviceShow.preview"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "serviceShow.openMapViewer" }),
    ).not.toBeInTheDocument();
  });

  it("honors an explicit preview override", () => {
    setup("WMS", service, { preview: <div>Custom preview</div> });

    expect(screen.getByText("Custom preview")).toBeInTheDocument();
    expect(screen.queryByText("Live preview WMS")).not.toBeInTheDocument();
  });
});
