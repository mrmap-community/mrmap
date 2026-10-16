import { render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import {
  AdminContext,
  RecordContextProvider,
  ResourceContextProvider,
  TextField,
} from "react-admin";
import { describe, expect, it, vi } from "vitest";
import ServiceOverview from "./ServiceOverview";
import type { ServiceProtocol } from "./ServiceDetailsCard";

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
    expect(screen.queryByText("Live preview WMS")).not.toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      expect.stringContaining("REQUEST=GetCapabilities"),
    );
  });

  it("keeps the service information and viewer action available when the preview is missing", () => {
    setup("WMS", { ...service, previewUrl: "" });

    expect(screen.getByText("serviceShow.previewUnavailable")).toBeInTheDocument();
    expect(screen.getByText(service.title)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "serviceShow.openMapViewer" }),
    ).toBeInTheDocument();
  });

  it.each(["WFS", "CSW"] as const)(
    "preserves the %s live preview without a WMS thumbnail or viewer action",
    (protocol) => {
      setup(protocol);

      expect(screen.getByText(`Live preview ${protocol}`)).toBeInTheDocument();
      expect(screen.queryByAltText("serviceShow.preview")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "serviceShow.openMapViewer" }),
      ).not.toBeInTheDocument();
    },
  );

  it("honors an explicit preview override", () => {
    setup("WMS", service, { preview: <div>Custom preview</div> });

    expect(screen.getByText("Custom preview")).toBeInTheDocument();
    expect(screen.queryByText("Live preview WMS")).not.toBeInTheDocument();
  });
});
