import { AdminContext, testDataProvider, type DataProvider } from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ElementInspection from "./ElementInspection";

vi.mock("../../../MapContainer/GeoJsonMap", () => ({
  default: () => <div data-testid="map" />,
}));
vi.mock("../../../Input/FeatureGroupEditor", () => ({ default: () => null }));
vi.mock("../RecordShow/RecordFields", () => ({ IncludedRecordFields: () => null }));

describe("element inspection data requests", () => {
  it.each([
    ["Layer", "WebMapService", "styles,referenceSystems,timeExtents"],
    ["FeatureType", "WebFeatureService", "referenceSystems,defaultReferenceSystem,outputFormats"],
  ] as const)("passes %s includes through react-admin to the data provider", async (resource, serviceResource, include) => {
    const getOne = vi.fn(async () => ({
      data: {
        id: "element-1",
        title: "Selected element",
        referenceSystems: [{ id: "1", stringRepresentation: "EPSG:4326" }],
      },
    }));
    render(
      <AdminContext dataProvider={testDataProvider({
        getOne: getOne as DataProvider["getOne"],
        getMany: async () => ({ data: [] }),
      })}>
        <ElementInspection resource={resource} id="element-1" serviceResource={serviceResource} />
      </AdminContext>,
    );

    expect(await screen.findByText("EPSG:4326")).toBeInTheDocument();
    expect(getOne).toHaveBeenCalledWith(resource, expect.objectContaining({
      id: "element-1",
      meta: { jsonApiParams: { include } },
    }));
    expect(screen.queryByText("#1")).not.toBeInTheDocument();
  });
});
