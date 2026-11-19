import type { ServiceProtocol } from "./ServiceDetailsCard";

import type { ComponentProps } from "react";
import {
  AdminContext,
  RecordContextProvider,
  ResourceContextProvider,
  testDataProvider,
  TextField,
} from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ServiceOverview from "./ServiceOverview";

// the owning organization is only asked for by a signed-in caller, since the
// organizations endpoint refuses everybody else (#833's public seam)
vi.mock("../../../../providers/authProvider", async (importOriginal) => ({
  ...(await importOriginal<
    typeof import("../../../../providers/authProvider")
  >()),
  getPermissionSnapshot: () =>
    Promise.resolve({
      roles: [],
      administeredOrganizationIds: [],
      isSuperuser: false,
    }),
}));

vi.mock("../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "https://mrmap.test",
  useHttpClientContext: () => ({
    api: {
      client: { request: () => new Promise(() => {}) },
      getOperation: () => ({}),
    },
  }),
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
  default: ({ label, protocol }: { label: string; protocol: string }) => (
    <button data-protocol={protocol}>{label}</button>
  ),
}));

vi.mock("../../WebFeatureService/Button/MapViewerButton", () => ({
  default: ({ label }: { label: string }) => (
    <button data-protocol="WFS">{label}</button>
  ),
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

/** the shown service as the api answers the `owner` relation of #733: an
 *  identifier of an organization, without its name */
const serviceWithOwner = { ...service, owner: { id: "901" } };

const setup = (
  protocol: ServiceProtocol,
  record = service,
  props: Partial<ComponentProps<typeof ServiceOverview>> = {},
  dataProvider?: ComponentProps<typeof AdminContext>["dataProvider"],
) =>
  render(
    <AdminContext
      dataProvider={dataProvider}
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

  it("loads the WFS thumbnail and offers the WFS viewer action without a live preview", () => {
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
      screen.getByRole("button", { name: "serviceShow.openMapViewer" }),
    ).toHaveAttribute("data-protocol", "WFS");
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

describe("the owning organization on a shown service (#733)", () => {
  it.each(["WMS", "WFS", "CSW"] as const)(
    "names the organization of the %s service it shows",
    async (protocol) => {
      const getList = vi.fn().mockResolvedValue({
        data: [
          { id: "901", stringRepresentation: "City of Springfields" },
        ],
        total: 1,
      });

      setup(
        protocol,
        serviceWithOwner,
        {},
        testDataProvider({ getList }),
      );

      expect(await screen.findByText("serviceShow.owner")).toBeInTheDocument();
      expect(screen.getByText("City of Springfields")).toBeInTheDocument();
    },
  );

  it("documents a service which names no owner", () => {
    // the fixture of the shown service asks the question and answers none,
    // which is what a service of before ownership was stored looks like
    setup("WMS");

    expect(screen.getByText("serviceShow.owner")).toBeInTheDocument();
    expect(screen.getByText("serviceShow.ownerNone")).toBeInTheDocument();
  });
});
