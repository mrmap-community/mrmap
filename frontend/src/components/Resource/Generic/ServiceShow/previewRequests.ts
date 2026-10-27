import type { RaRecord } from "react-admin";

import { API_BASE_URL } from "../../../../context/HttpClientContext";
import { updateOrAppendSearchParam } from "../../../../ows-lib/OwsContext/utils";
import { getAuthToken } from "../../../../providers/authProvider";

export type PreviewProtocol = "WMS" | "WFS";

/** The number of features a feature preview asks for, like the map viewer keeps it. */
export const FEATURE_LIMIT = 500;

/**
 * The mrmap security proxy endpoint of a service. Secured services must only be
 * requested through it: it authenticates upstream with the stored service
 * credentials and applies the spatial security rules of the requesting user.
 */
export const proxyUrl = (protocol: PreviewProtocol, serviceId: string): URL =>
  new URL(
    `/mrmap-proxy/${protocol === "WMS" ? "wms" : "wfs"}/${serviceId}`,
    API_BASE_URL,
  );

/** The stored operation urls answer as numbers of the registry enums or as their labels. */
const isGet = (value: unknown): boolean =>
  value === 1 || String(value).toLowerCase() === "get";

const isOperation = (value: unknown, code: number, label: string): boolean =>
  value === code || String(value).toLowerCase() === label.toLowerCase();

/**
 * The remote base url the registry stored for the GetMap respective GetFeature
 * operation of a service, the base a not secured service is asked directly.
 */
export const remoteOperationUrl = (
  service: RaRecord | undefined,
  protocol: PreviewProtocol,
): URL | undefined => {
  const operation = (service?.operationUrls as RaRecord[] | undefined)?.find(
    (entry) =>
      isGet(entry.method) &&
      (protocol === "WMS"
        ? isOperation(entry.operation, 20, "GetMap")
        : isOperation(entry.operation, 30, "GetFeature")),
  );
  return operation?.url ? new URL(String(operation.url)) : undefined;
};

/** Only a request to the MrMap origin carries the MrMap token, never one to a remote service. */
export const requestHeaders = (url: URL): Headers | undefined => {
  const token = getAuthToken()?.token;
  if (!token || url.origin !== new URL(API_BASE_URL, window.location.href).origin) {
    return undefined;
  }
  return new Headers({ Authorization: `Token ${String(token)}` });
};

const set = (params: URLSearchParams, key: string, value: string) =>
  updateOrAppendSearchParam(params, key, value);

/**
 * A GetMap of exactly one layer within one WGS84 extent, the same request shape
 * the backend of the retired preview operation built: WGS84 as the only CRS,
 * transparent, and the extent in the axis order the version declares.
 */
export const buildWmsGetMapUrl = (
  base: URL,
  {
    identifier,
    version,
    extent,
    width = 800,
    height = 400,
    format = "image/png",
  }: {
    identifier: string;
    version: string;
    extent: number[];
    width?: number;
    height?: number;
    format?: string;
  },
): URL => {
  const url = new URL(base.href);
  const params = url.searchParams;
  set(params, "SERVICE", "WMS");
  set(params, "REQUEST", "GetMap");
  set(params, "VERSION", version);
  set(params, "LAYERS", identifier);
  set(params, "STYLES", "");
  set(params, "FORMAT", format);
  set(params, "TRANSPARENT", "TRUE");
  set(params, version === "1.3.0" ? "CRS" : "SRS", "EPSG:4326");
  set(params, "WIDTH", String(width));
  set(params, "HEIGHT", String(height));
  set(
    params,
    "BBOX",
    (version === "1.3.0"
      ? [extent[1], extent[0], extent[3], extent[2]]
      : extent
    ).join(","),
  );
  return url;
};

/**
 * A bounded GetFeature of exactly one feature type within one WGS84 extent. The
 * feature types must advertise a GeoJSON answer - a GML answer is not converted
 * in the browser - which the caller reads from the stored output formats.
 */
export const buildWfsGetFeatureUrl = (
  base: URL,
  {
    identifier,
    version,
    extent,
    outputFormat,
    limit = FEATURE_LIMIT,
  }: {
    identifier: string;
    version: string;
    extent: number[];
    outputFormat: string;
    limit?: number;
  },
): URL => {
  const url = new URL(base.href);
  const params = url.searchParams;
  const versionedBbox = version !== "1.0.0";
  set(params, "SERVICE", "WFS");
  set(params, "REQUEST", "GetFeature");
  set(params, "VERSION", version);
  set(
    params,
    version.startsWith("2.") ? "TYPENAMES" : "TYPENAME",
    identifier,
  );
  set(params, "SRSNAME", "EPSG:4326");
  set(params, "OUTPUTFORMAT", outputFormat);
  set(
    params,
    version.startsWith("2.") ? "COUNT" : "MAXFEATURES",
    String(limit),
  );
  set(
    params,
    "BBOX",
    versionedBbox
      ? [extent[1], extent[0], extent[3], extent[2]].join(",") + ",EPSG:4326"
      : extent.join(","),
  );
  return url;
};

/** The first stored output format of a feature type which answers GeoJSON. */
export const geoJsonOutputFormat = (
  featureType: RaRecord | undefined,
): string | undefined => {
  const formats = (featureType?.outputFormats as RaRecord[] | undefined) ?? [];
  const candidate = formats.find((entry) =>
    String(entry.mimeType ?? entry.stringRepresentation ?? "")
      .toLowerCase()
      .includes("json"),
  );
  return candidate
    ? String(candidate.mimeType ?? candidate.stringRepresentation)
    : undefined;
};
