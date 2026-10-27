import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildWfsGetFeatureUrl,
  buildWmsGetMapUrl,
  geoJsonOutputFormat,
  proxyUrl,
  remoteOperationUrl,
  requestHeaders,
} from "./previewRequests";

const state = vi.hoisted(() => ({
  token: undefined as string | undefined,
}));

vi.mock("../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "http://localhost:8000/api/",
}));

vi.mock("../../../../providers/authProvider", () => ({
  getAuthToken: () => (state.token ? { token: state.token } : null),
}));

const extent = [8.1, 49.0, 8.5, 49.4];

beforeEach(() => {
  state.token = undefined;
});

describe("preview request building", () => {
  it("routes a secured service over the mrmap proxy of its protocol", () => {
    expect(proxyUrl("WMS", "service-1").href).toBe(
      "http://localhost:8000/mrmap-proxy/wms/service-1",
    );
    expect(proxyUrl("WFS", "service-1").href).toBe(
      "http://localhost:8000/mrmap-proxy/wfs/service-1",
    );
  });

  it("reads the stored GetMap respective GetFeature url of an unsecured service", () => {
    const service = {
      id: "1",
      operationUrls: [
        { method: 1, operation: 1, url: "https://remote/capabilities" },
        { method: 1, operation: 20, url: "https://remote/wms" },
        { method: 1, operation: 30, url: "https://remote/wfs" },
        { method: 2, operation: 20, url: "https://remote/wms-post" },
      ],
    };
    expect(remoteOperationUrl(service, "WMS")?.href).toBe("https://remote/wms");
    expect(remoteOperationUrl(service, "WFS")?.href).toBe("https://remote/wfs");
    // the enums may answer as labels instead of numbers
    expect(
      remoteOperationUrl(
        {
          id: "service-x",
          operationUrls: [
            { method: "Get", operation: "GetMap", url: "https://remote/wms" },
          ],
        },
        "WMS",
      )?.href,
    ).toBe("https://remote/wms");
    expect(
      remoteOperationUrl({ id: "service-x", operationUrls: [] }, "WFS"),
    ).toBeUndefined();
  });

  it("carries the MrMap token only to the MrMap origin", () => {
    state.token = "secret";
    expect(
      requestHeaders(new URL("http://localhost:8000/mrmap-proxy/wms/1"))?.get(
        "Authorization",
      ),
    ).toBe("Token secret");
    expect(requestHeaders(new URL("https://remote/wms"))).toBeUndefined();
    state.token = undefined;
    expect(requestHeaders(new URL("http://localhost:8000/mrmap-proxy/wms/1"))).toBeUndefined();
  });

  it("asks a WMS 1.3.0 in latitude/longitude axis order with the CRS parameter", () => {
    const url = buildWmsGetMapUrl(new URL("https://remote/wms"), {
      identifier: "wg:topographic",
      version: "1.3.0",
      extent,
    });
    const params = url.searchParams;
    expect(params.get("BBOX")).toBe("49,8.1,49.4,8.5");
    expect(params.get("CRS")).toBe("EPSG:4326");
    expect(params.get("SRS")).toBeNull();
    expect(params.get("LAYERS")).toBe("wg:topographic");
    expect(params.get("TRANSPARENT")).toBe("TRUE");
    expect(params.get("FORMAT")).toBe("image/png");
    expect(params.get("REQUEST")).toBe("GetMap");
  });

  it("asks a WMS 1.1.1 in longitude/latitude order with the SRS parameter", () => {
    const url = buildWmsGetMapUrl(new URL("https://remote/wms"), {
      identifier: "layer",
      version: "1.1.1",
      extent,
      format: "image/jpeg",
      width: 640,
      height: 320,
    });
    const params = url.searchParams;
    expect(params.get("BBOX")).toBe("8.1,49,8.5,49.4");
    expect(params.get("SRS")).toBe("EPSG:4326");
    expect(params.get("FORMAT")).toBe("image/jpeg");
    expect(params.get("WIDTH")).toBe("640");
    expect(params.get("HEIGHT")).toBe("320");
  });

  it("asks a WFS 2.0.0 with type names, count and a declared bbox crs", () => {
    const url = buildWfsGetFeatureUrl(new URL("https://remote/wfs"), {
      identifier: "units",
      version: "2.0.0",
      extent,
      outputFormat: "application/json",
    });
    const params = url.searchParams;
    expect(params.get("TYPENAMES")).toBe("units");
    expect(params.get("TYPENAME")).toBeNull();
    expect(params.get("COUNT")).toBe("500");
    expect(params.get("MAXFEATURES")).toBeNull();
    expect(params.get("BBOX")).toBe("49,8.1,49.4,8.5,EPSG:4326");
    expect(params.get("SRSNAME")).toBe("EPSG:4326");
    expect(params.get("OUTPUTFORMAT")).toBe("application/json");
  });

  it("asks a WFS 1.1.0 with the singular type name and max features", () => {
    const params = buildWfsGetFeatureUrl(new URL("https://remote/wfs"), {
      identifier: "units",
      version: "1.1.0",
      extent,
      outputFormat: "text/json",
    }).searchParams;
    expect(params.get("TYPENAME")).toBe("units");
    expect(params.get("MAXFEATURES")).toBe("500");
    expect(params.get("BBOX")).toBe("49,8.1,49.4,8.5,EPSG:4326");
  });

  it("asks a WFS 1.0.0 without the bbox crs which does not know one", () => {
    const params = buildWfsGetFeatureUrl(new URL("https://remote/wfs"), {
      identifier: "units",
      version: "1.0.0",
      extent,
      outputFormat: "application/json",
    }).searchParams;
    expect(params.get("BBOX")).toBe("8.1,49,8.5,49.4");
    expect(params.get("TYPENAME")).toBe("units");
  });

  it("picks a stored GeoJSON output format of a feature type", () => {
    expect(
      geoJsonOutputFormat({
        id: "element-x",
        outputFormats: [
          { mimeType: "gml32", stringRepresentation: "GML 3.2" },
          { mimeType: "application/json", stringRepresentation: "JSON" },
        ],
      }),
    ).toBe("application/json");
    expect(
      geoJsonOutputFormat({
        id: "element-x",
        outputFormats: [{ mimeType: "gml32", stringRepresentation: "GML 3.2" }],
      }),
    ).toBeUndefined();
    expect(geoJsonOutputFormat(undefined)).toBeUndefined();
  });
});
