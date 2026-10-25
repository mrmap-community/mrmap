import {
  AdminContext,
  type RaRecord,
  RecordContextProvider,
  ResourceContextProvider,
  SelectField,
  TextField,
  testDataProvider,
} from "react-admin";
import { MemoryRouter } from "react-router-dom";

import { render, screen } from "@testing-library/react";
import polyglotI18nProvider from "ra-i18n-polyglot";
import { describe, expect, it, vi } from "vitest";

import de from "../../../../i18n/de";
import en from "../../../../i18n/en";
import ServiceDetailsCard from "./ServiceDetailsCard";

vi.mock("../../../../jsonapi/hooks/useFieldsForOperation", () => ({
  useFieldsForOperation: () => [
    ...["id", "title", "abstract"].map((source) => ({
      component: TextField,
      props: { source, label: source },
    })),
    {
      component: SelectField,
      props: { source: "version", choices: [{ id: 0, name: "1.3.0" }] },
    },
  ],
}));
vi.mock("./ServicePreviewImage", () => ({ default: () => null }));
vi.mock("./ActivateServiceButton", () => ({ default: () => null }));
vi.mock("../../WebMapService/Button/MapViewerButton", () => ({
  default: ({ protocol }: { protocol: string }) => <span data-testid="map-viewer" data-protocol={protocol} />,
}));
// the WFS button asks for the feature types of the service, which the card itself must not answer
vi.mock("../../WebFeatureService/Button/MapViewerButton", () => ({
  default: ({ label }: { label?: string }) => (
    <span data-testid="wfs-mapviewer">{label}</span>
  ),
}));

const renderDetails = (version?: number, locale = "en") =>
  render(
    <AdminContext
      i18nProvider={polyglotI18nProvider(
        () => (locale === "de" ? de : en),
        locale,
      )}
    >
      <ResourceContextProvider value="WebMapService">
        <RecordContextProvider
          value={{
            id: "service",
            title: "Weather WMS",
            abstract: "Weather maps",
            version,
          }}
        >
          <ServiceDetailsCard protocol="WMS" />
        </RecordContextProvider>
      </ResourceContextProvider>
    </AdminContext>,
  );

/** the card of a service which a screen of services only selects */
const selectedCard = (
  record: Record<string, unknown>,
  dataProvider: ReturnType<typeof testDataProvider>,
) => (
  <MemoryRouter>
    <AdminContext
      i18nProvider={polyglotI18nProvider(() => en, "en")}
      dataProvider={dataProvider}
    >
      <ResourceContextProvider value="WebMapService">
        <RecordContextProvider value={record}>
          <ServiceDetailsCard protocol="WMS" attention openDetails />
        </RecordContextProvider>
      </ResourceContextProvider>
    </AdminContext>
  </MemoryRouter>
);

/** the runs and jobs a screen of services answers for one service */
const answersOutcome = (resource: string) => ({
  data: (resource.endsWith("UpdateJob")
    ? [{ id: "job", doneAt: "2026-10-07T12:15:00Z", status: "Succeeded" }]
    : [
        { id: "run", dateDone: "2026-10-08T06:00:00Z", success: true },
      ]) as RaRecord[],
  total: 1,
});

describe("ServiceDetailsCard labels", () => {
  it.each(['WMS', 'WFS'] as const)('offers the map viewer for a %s service', (protocol) => {
    render(
      <AdminContext>
        <ResourceContextProvider value={protocol === 'WFS' ? 'WebFeatureService' : 'WebMapService'}>
          <RecordContextProvider value={{ id: 'service', title: 'Service' }}>
            <ServiceDetailsCard protocol={protocol} />
          </RecordContextProvider>
        </ResourceContextProvider>
      </AdminContext>,
    );
    if (protocol === 'WFS') {
      expect(screen.getByTestId('wfs-mapviewer')).toBeInTheDocument();
      expect(screen.queryByTestId('map-viewer')).not.toBeInTheDocument();
    } else {
      expect(screen.getByTestId('map-viewer')).toHaveAttribute('data-protocol', protocol);
      expect(screen.queryByTestId('wfs-mapviewer')).not.toBeInTheDocument();
    }
  });
  it("shows readable labels and hides an absent version", () => {
    renderDetails();
    for (const label of ["ID", "Title", "Abstract"])
      expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.queryByText("Version")).not.toBeInTheDocument();
  });

  it("keeps a version whose valid enum value is zero", () => {
    renderDetails(0);
    expect(screen.getByText("Version")).toBeInTheDocument();
    expect(screen.getByText("1.3.0")).toBeInTheDocument();
  });

  it("translates the labels into German", () => {
    renderDetails(undefined, "de");
    expect(screen.getByText("Titel")).toBeInTheDocument();
    expect(screen.getByText("Beschreibung")).toBeInTheDocument();
  });

  it("opens a web feature service in the map viewer from its own screen", () => {
    render(
      <AdminContext i18nProvider={polyglotI18nProvider(() => en, "en")}>
        <ResourceContextProvider value="WebFeatureService">
          <RecordContextProvider value={{ id: "wfs", title: "Buildings", version: 2 }}>
            <ServiceDetailsCard protocol="WFS" />
          </RecordContextProvider>
        </ResourceContextProvider>
      </AdminContext>,
    );
    // the WFS screen answers the viewer action of its own protocol, and not the WMS one
    expect(screen.getByTestId("wfs-mapviewer")).toHaveTextContent(
      "serviceShow.openMapViewer",
    );
  });

  it("answers no feature type viewer action to a web map service", () => {
    renderDetails();
    expect(screen.queryByTestId("wfs-mapviewer")).not.toBeInTheDocument();
  });
});

describe("ServiceDetailsCard of a selected service", () => {
  it("asks the outcome of the runs and the jobs of the selected service", async () => {
    const getList = vi
      .fn()
      .mockImplementation(async (resource: string) => answersOutcome(resource));
    const { rerender } = render(
      selectedCard(
        { id: "service-1", title: "Weather WMS" },
        testDataProvider({ getList }),
      ),
    );
    expect(await screen.findByText(/Succeeded/)).toBeInTheDocument();
    expect(screen.getByText(/passed/)).toBeInTheDocument();
    expect(screen.getByText("last monitoring run:")).toBeInTheDocument();
    expect(screen.getByText("last update:")).toBeInTheDocument();
    // the date of a monitoring run is the point in time it was done at
    expect(screen.getByText(/10\/8\/2026/)).toBeInTheDocument();
    expect(getList).toHaveBeenCalledWith(
      "WebMapServiceMonitoringRun",
      expect.objectContaining({
        pagination: { page: 1, perPage: 1 },
        sort: { field: "dateDone", order: "DESC" },
      }),
    );

    // a service which is selected afterwards asks its own runs and jobs
    rerender(
      selectedCard(
        { id: "service-2", title: "Orthophotos" },
        testDataProvider({
          getList: vi.fn().mockImplementation(async (resource: string) => ({
            data: (resource.endsWith("UpdateJob")
              ? [
                  {
                    id: "job",
                    doneAt: "2026-10-09T08:00:00Z",
                    status: "Failed",
                  },
                ]
              : []) as RaRecord[],
            total: resource.endsWith("UpdateJob") ? 1 : 0,
          })),
        }),
      ),
    );
    expect(await screen.findByText(/Failed/)).toBeInTheDocument();
    expect(screen.queryByText(/Succeeded/)).not.toBeInTheDocument();
    expect(screen.getByText("not recorded yet")).toBeInTheDocument();
  });

  it("names the states which need attention and the way to the service", () => {
    render(
      selectedCard(
        {
          id: "service-1",
          title: "Weather WMS",
          monitoringFailed: true,
          updateReviewRequired: true,
        },
        testDataProvider({
          getList: vi
            .fn()
            .mockImplementation(async () =>
              answersOutcome("WebMapServiceUpdateJob"),
            ),
        }),
      ),
    );
    expect(screen.getByText("Monitoring failed")).toBeInTheDocument();
    expect(screen.getByText("Review required")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open details" })).toHaveAttribute(
      "href",
      "/WebMapService/service-1/show",
    );
  });

  it("names a run or job which cannot be read instead of pretending it is absent", async () => {
    render(
      selectedCard(
        { id: "service-1", title: "Weather WMS" },
        testDataProvider({
          getList: vi.fn().mockRejectedValue(new Error("forbidden")),
        }),
      ),
    );
    expect(await screen.findAllByText("not readable")).toHaveLength(2);
  });

  it("asks nothing and shows no outcome of a service which is not selected", () => {
    const getList = vi.fn().mockResolvedValue({ data: [], total: 0 });
    render(
      <AdminContext
        i18nProvider={polyglotI18nProvider(() => en, "en")}
        dataProvider={testDataProvider({ getList })}
      >
        <ResourceContextProvider value="WebMapService">
          <ServiceDetailsCard protocol="WMS" />
        </ResourceContextProvider>
      </AdminContext>,
    );
    expect(
      screen.getByText("Select a service to see its details."),
    ).toBeInTheDocument();
    expect(screen.queryByText("last monitoring run:")).not.toBeInTheDocument();
    expect(screen.queryByText("No alerts")).not.toBeInTheDocument();
    expect(getList).not.toHaveBeenCalled();
  });
});
