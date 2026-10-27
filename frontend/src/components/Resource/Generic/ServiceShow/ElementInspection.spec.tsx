import type { ReactNode } from "react";
import { RecordContextProvider, useRecordContext } from "react-admin";
import { MemoryRouter } from "react-router-dom";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ElementInspection from "./ElementInspection";

const state = vi.hoisted(() => ({
  record: undefined as Record<string, unknown> | undefined,
  isPending: false,
  error: undefined as Error | undefined,
  metadataRecords: [] as Record<string, unknown>[],
  hasEdit: true,
  getOneMeta: undefined as Record<string, unknown> | undefined,
}));

vi.mock("react-admin", async () => ({
  ...(await vi.importActual<typeof import("react-admin")>("react-admin")),
  useTranslate: () => (key: string) => key,
  useGetOne: (_resource: string, params: { meta?: unknown }) => {
    state.getOneMeta = params.meta as Record<string, unknown>;
    return {
      data: state.record,
      isPending: state.isPending,
      error: state.error,
      refetch: vi.fn(),
    };
  },
  useGetMany: () => ({ data: state.metadataRecords }),
  useResourceDefinition: () => ({ hasEdit: state.hasEdit }),
  Loading: () => <span>loading</span>,
  Link: ({ to, children }: { to: string; children?: ReactNode }) => (
    <a href={to}>{children}</a>
  ),
}));

vi.mock("../../../MapContainer/GeoJsonMap", () => ({
  default: () => <div data-testid="map" />,
}));

vi.mock("../../../Input/FeatureGroupEditor", () => ({
  default: () => <div data-testid="geometry" />,
}));

vi.mock("../RecordShow/RecordFields", () => ({
  IncludedRecordFields: ({ record, sources }: { record: Record<string, unknown>; sources: string[] }) => (
    <span>{String(record?.[sources[0]] ?? "—")}</span>
  ),
}));

const layer = {
  id: "layer-1",
  stringRepresentation: "roads",
  abstract: "",
  bbox: { type: "Polygon", coordinates: [[[6, 49], [7, 49], [7, 50], [6, 50], [6, 49]]] },
  isQueryable: true,
  isOpaque: null,
  scaleMin: 500,
  scaleMax: null,
  isSecured: false,
  isSpatialSecured: null,
  styles: [{ id: "style-1", stringRepresentation: "standard" }],
  referenceSystems: [{ id: "1", stringRepresentation: "EPSG:25832" }],
  timeExtents: [{ id: "time-1", begin: "2020-01-01T00:00:00Z" }],
  datasetMetadata: [{ id: "metadata-1" }],
};

const featureType = {
  id: "featuretype-1",
  stringRepresentation: "buildings",
  abstract: "Buildings of the city.",
  outputFormats: [{ id: "1", stringRepresentation: "application/json" }],
  referenceSystems: [{ id: "2", stringRepresentation: "EPSG:4326" }],
  describeFeatureTypeDocument: "",
  isSecured: null,
  isSpatialSecured: null,
};

/** Tells which record an inspection gave to one of its actions. */
const RecordName = ({ label }: { label: string }) => {
  const record = useRecordContext();
  return <span>{label} {String(record?.stringRepresentation)}</span>;
};

const showLayer = () =>
  render(
    <MemoryRouter>
      <ElementInspection
        resource="Layer"
        id="layer-1"
        serviceResource="WebMapService"
        serviceId="wms-1"
      />
    </MemoryRouter>,
  );

const showFeatureType = () =>
  render(
    <MemoryRouter>
      <ElementInspection
        resource="FeatureType"
        id="featuretype-1"
        serviceResource="WebFeatureService"
        serviceId="wfs-1"
      />
    </MemoryRouter>,
  );

beforeEach(() => {
  state.record = undefined;
  state.isPending = false;
  state.error = undefined;
  state.metadataRecords = [];
  state.hasEdit = true;
  state.getOneMeta = undefined;
});

describe("element inspection", () => {
  it("asks to select an element while none is selected", () => {
    render(
      <MemoryRouter>
        <ElementInspection resource="Layer" serviceResource="WebMapService" />
      </MemoryRouter>,
    );
    expect(screen.getByText("layerInspection.select")).toBeInTheDocument();
  });

  it("names the includes the layer answers are read from", () => {
    state.record = layer;
    state.metadataRecords = [{ id: "metadata-1", stringRepresentation: "Roads dataset" }];
    showLayer();
    expect(state.getOneMeta).toEqual({
      jsonApiParams: { include: "styles,referenceSystems,timeExtents" },
    });
    expect(screen.getByTestId("map")).toBeInTheDocument();
    expect(screen.getByText("EPSG:25832")).toBeInTheDocument();
    expect(screen.getByText("2020-01-01T00:00:00Z")).toBeInTheDocument();
    expect(screen.getByText("Roads dataset")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "layerInspection.edit" }),
    ).toHaveAttribute("href", "/Layer/layer-1/edit");
    expect(
      screen.getByRole("link", { name: "layerInspection.rules" }),
    ).toHaveAttribute("href", "/WebMapService/wms-1/show/AllowedWebMapServiceOperation");
  });

  it("states yes, no and unknown for the parsed constraints", () => {
    state.record = layer;
    showLayer();
    expect(screen.getByText("layerInspection.yes")).toBeInTheDocument();
    expect(screen.getAllByText("layerInspection.unknown").length).toBeGreaterThan(0);
    expect(screen.getByText("standard")).toBeInTheDocument();
    expect(screen.getByText("layerInspection.noAbstract")).toBeInTheDocument();
  });

  it("labels access-rule flags and distinguishes false from unavailable", () => {
    state.record = { ...layer, isSecured: false, isSpatialSecured: false };
    const { unmount } = showLayer();
    expect(screen.getByText("layerInspection.secured: layerInspection.no")).toBeInTheDocument();
    expect(screen.getByText("layerInspection.spatialSecured: layerInspection.no")).toBeInTheDocument();
    unmount();
    state.record = { ...featureType, isSecured: true, isSpatialSecured: null };
    showFeatureType();
    expect(screen.getByText("layerInspection.secured: layerInspection.yes")).toBeInTheDocument();
    expect(screen.getByText("layerInspection.spatialSecured: layerInspection.unknown")).toBeInTheDocument();
  });

  it("states the missing coverage of a layer explicitly", () => {
    state.record = { ...layer, bbox: null };
    showLayer();
    expect(screen.getByText("layerInspection.noCoverage")).toBeInTheDocument();
  });

  it("uses the inherited coverage of a layer without its own bounding box", () => {
    state.record = { ...layer, bbox: null, bboxLatLon: layer.bbox };
    showLayer();
    expect(screen.getByTestId("map")).toBeInTheDocument();
    expect(screen.queryByText("layerInspection.noCoverage")).not.toBeInTheDocument();
  });

  it("offers no edit destination when the user may not edit", () => {
    state.record = layer;
    state.hasEdit = false;
    showLayer();
    expect(
      screen.queryByRole("link", { name: "layerInspection.edit" }),
    ).not.toBeInTheDocument();
  });

  it("shows formats and the missing description of a feature type", () => {
    state.record = featureType;
    showFeatureType();
    expect(screen.getByText("application/json")).toBeInTheDocument();
    expect(screen.getByText("Buildings of the city.")).toBeInTheDocument();
    expect(screen.getByText("layerInspection.noDescription")).toBeInTheDocument();
    expect(screen.getByText("layerInspection.noFeatureTypeCoverage")).toBeInTheDocument();
    expect(state.getOneMeta).toEqual({
      jsonApiParams: {
        include: "referenceSystems,defaultReferenceSystem,outputFormats",
      },
    });
  });

  it("shows the coverage and default CRS returned for a feature type", () => {
    state.record = {
      ...featureType,
      bboxLatLon: layer.bbox,
      referenceSystems: [],
      defaultReferenceSystem: { id: "1", stringRepresentation: "EPSG:25832" },
    };
    showFeatureType();
    expect(screen.getByTestId("map")).toBeInTheDocument();
    expect(screen.getByText("EPSG:25832")).toBeInTheDocument();
    expect(screen.queryByText("layerInspection.noFeatureTypeCoverage")).not.toBeInTheDocument();
  });

  it("shows a default CRS only once when it is also an available reference system", () => {
    state.record = {
      ...featureType,
      defaultReferenceSystem: featureType.referenceSystems[0],
    };
    showFeatureType();
    expect(screen.getAllByText("EPSG:4326")).toHaveLength(1);
  });

  it("answers loading and error states for the selected element", () => {
    state.isPending = true;
    const { unmount } = showLayer();
    expect(screen.getByText("loading")).toBeInTheDocument();
    unmount();
    state.isPending = false;
    state.error = new Error("gone");
    showLayer();
    expect(screen.getByText("layerInspection.loadError")).toBeInTheDocument();
  });

  it("gives the inspected record to the preview action which asks for it", () => {
    state.record = layer;
    render(
      <MemoryRouter>
        <ElementInspection
          resource="Layer"
          id="layer-1"
          serviceResource="WebMapService"
          previewAction={(record) => (
            <RecordContextProvider value={record}>
              <RecordName label="preview of" />
            </RecordContextProvider>
          )}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("preview of roads")).toBeInTheDocument();
  });

  it("shows the history of the inspected record", () => {
    state.record = layer;
    render(
      <MemoryRouter>
        <ElementInspection
          resource="Layer"
          id="layer-1"
          serviceResource="WebMapService"
          history={(record) => (
            <RecordContextProvider value={record}>
              <RecordName label="history of" />
            </RecordContextProvider>
          )}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("history of roads")).toBeInTheDocument();
    expect(screen.queryByText("preview of roads")).not.toBeInTheDocument();
  });
});
