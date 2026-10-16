import { useQuery } from "@tanstack/react-query";
import {
  API_BASE_URL,
  useHttpClientContext,
} from "../../../../../context/HttpClientContext";
import useOperation from "../../../../../jsonapi/hooks/useOperation";
import { updateOrAppendSearchParam } from "../../../../../ows-lib/OwsContext/utils";
import { getAuthToken } from "../../../../../providers/authProvider";
import type { FeatureCollection } from "geojson";

export type Protocol = "WMS" | "WFS" | "CSW";
export const serviceResource = {
  WMS: "WebMapService",
  WFS: "WebFeatureService",
  CSW: "CatalogueService",
};
export interface PreviewLink {
  protocol: "WMS" | "WFS";
  serviceId: string;
  selection: string;
  title: string;
}
/** A prefilled identify request against `mrmap-proxy`, answered in the browser. */
export interface IdentifyLink {
  url: string;
  infoFormat: string;
}
/** Structurally the preview map viewport, kept local to avoid an import cycle. */
export interface IdentifyViewport {
  bbox: string;
  width: number;
  height: number;
}
export interface LiveRecord {
  identifier: string;
  title?: string;
  abstract?: string;
  extent: number[] | null;
  previews: PreviewLink[];
}
export interface PreviewResult {
  source?: string;
  fetchedAt?: string;
  discovery?: "stored";
  configuration?: { extent: number[] | null; queryable: boolean };
  image?: string;
  features?: FeatureCollection;
  limited?: boolean;
  limit?: number;
  records?: LiveRecord[];
  start?: number;
  next?: number;
  matched?: number;
  pageSize?: number;
  /**
   * Same-origin security proxy url for a WMS identify, prefilled by the backend.
   * The browser performs the request itself, so spatial security and the stored
   * credentials stay on the server side.
   */
  identify?: IdentifyLink | null;
}

/**
 * The identify body the browser fetched from the security proxy. Markup is never part of it,
 * only the raw text and the media type it has to be interpreted with.
 */
export interface IdentifyResult {
  info: string;
  contentType?: string;
}
export class PreviewFailure extends Error {
  constructor(public code: string) {
    super(code);
  }
}

export const usePreview = (
  protocol: Protocol,
  id: string,
  params: Record<string, string | number>,
  enabled = true,
) => {
  const { api } = useHttpClientContext();
  const operationId = `preview_${serviceResource[protocol]}`;
  const operation = useOperation(operationId);
  const query = useQuery<PreviewResult, PreviewFailure>({
    queryKey: ["livePreview", protocol, id, params],
    enabled: enabled && Boolean(api && operation),
    retry: false,
    gcTime: 0,
    staleTime: 0,
    queryFn: async ({ signal }) => {
      // Debounce viewport changes and cancel the timer with obsolete work.
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => {
          signal.removeEventListener("abort", cancel);
          resolve();
        }, 250);
        const cancel = () => {
          clearTimeout(timer);
          reject(new DOMException("Aborted", "AbortError"));
        };
        signal.addEventListener("abort", cancel, { once: true });
      });
      if (!api || signal.aborted)
        throw new DOMException("Aborted", "AbortError");
      const config = api.getAxiosConfigForOperation(operationId, [
        { id, ...params },
        undefined,
        { signal },
      ]);
      const endpoint = new URL(
        config.url ?? "",
        config.baseURL ?? API_BASE_URL,
      );
      if (endpoint.origin !== new URL(API_BASE_URL).origin)
        throw new PreviewFailure("denied");
      const token = getAuthToken()?.token;
      config.headers = {
        Accept: "application/json",
        ...(token ? { Authorization: `Token ${token}` } : {}),
      };
      try {
        const response = await api.client.request<PreviewResult>(config);
        if (signal.aborted) throw new DOMException("Aborted", "AbortError");
        return response.data;
      } catch (error) {
        if (signal.aborted) throw error;
        const response = (
          error as { response?: { status?: number; data?: { error?: string } } }
        ).response;
        throw new PreviewFailure(
          response?.data?.error ??
            (response?.status === 403 || response?.status === 401
              ? "denied"
              : "unavailable"),
        );
      }
    },
  });
  return { ...query, supported: Boolean(operation) };
};

/**
 * Completes the url the backend generated with the viewport and the pixel of the identify.
 *
 * WMS 1.3.0 declares the bbox in the axis order of the CRS, which is latitude/longitude for
 * EPSG:4326, and renamed the pixel to I/J. Both pixel spellings are sent because servers
 * differ, exactly like in the map viewer.
 */
export const identifyUrl = (
  link: IdentifyLink,
  viewport: IdentifyViewport,
  x: number,
  y: number,
) => {
  const url = new URL(link.url, API_BASE_URL);
  const params = url.searchParams;
  const version = params.get("VERSION") ?? params.get("version") ?? "";
  const [west, south, east, north] = viewport.bbox.split(",");
  updateOrAppendSearchParam(
    params,
    "BBOX",
    version === "1.3.0" ? [south, west, north, east].join(",") : viewport.bbox,
  );
  updateOrAppendSearchParam(params, "WIDTH", String(viewport.width));
  updateOrAppendSearchParam(params, "HEIGHT", String(viewport.height));
  const column = String(Math.round(x));
  const row = String(Math.round(y));
  updateOrAppendSearchParam(params, "X", column);
  updateOrAppendSearchParam(params, "Y", row);
  updateOrAppendSearchParam(params, "I", column);
  updateOrAppendSearchParam(params, "J", row);
  return url;
};

/** Recognize an OGC exception report, which the proxy also answers with on a 200. */
const isOgcException = (body: string) => {
  if (!body.trimStart().startsWith("<") || !body.includes("xception"))
    return false;
  try {
    const parsed = new DOMParser().parseFromString(body, "application/xml");
    return Array.from(parsed.getElementsByTagName("*")).some(
      (element) =>
        element.localName === "ServiceException" ||
        element.localName === "ExceptionReport",
    );
  } catch {
    return false;
  }
};

/**
 * Performs the identify against the security proxy url of the preview response.
 *
 * The body is returned as text and typed by its media type, so only the caller decides how
 * to render it. Markup is never executed and no credential is sent to another origin.
 */
export const useIdentify = (
  link?: IdentifyLink | null,
  viewport?: IdentifyViewport,
  pixel?: { x: number; y: number },
) => {
  const { api } = useHttpClientContext();
  const url =
    link && viewport && pixel
      ? identifyUrl(link, viewport, pixel.x, pixel.y).href
      : undefined;
  const query = useQuery<IdentifyResult, PreviewFailure>({
    queryKey: ["liveIdentify", url],
    enabled: Boolean(api && url),
    retry: false,
    gcTime: 0,
    staleTime: 0,
    queryFn: async ({ signal }) => {
      if (!link || !url) throw new PreviewFailure("malformed");
      if (new URL(url).origin !== new URL(API_BASE_URL).origin)
        throw new PreviewFailure("denied");
      const token = getAuthToken()?.token;
      try {
        const response = await fetch(url, {
          signal,
          headers: {
            Accept: link.infoFormat,
            ...(token ? { Authorization: `Token ${token}` } : {}),
          },
        });
        if (response.status === 401 || response.status === 403)
          throw new PreviewFailure("denied");
        if (!response.ok) throw new PreviewFailure("unavailable");
        const body = await response.text();
        if (isOgcException(body)) throw new PreviewFailure("ogc");
        return {
          info: body,
          contentType: response.headers.get("content-type") ?? link.infoFormat,
        };
      } catch (error) {
        if (signal.aborted) throw error;
        if (error instanceof PreviewFailure) throw error;
        throw new PreviewFailure("unavailable");
      }
    },
  });
  return query;
};

