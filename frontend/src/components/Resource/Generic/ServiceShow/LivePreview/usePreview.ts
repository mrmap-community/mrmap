import { useQuery } from "@tanstack/react-query";
import {
  API_BASE_URL,
  useHttpClientContext,
} from "../../../../../context/HttpClientContext";
import useOperation from "../../../../../jsonapi/hooks/useOperation";
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
export interface LiveRecord {
  identifier: string;
  title?: string;
  abstract?: string;
  extent: number[] | null;
  previews: PreviewLink[];
}
export interface PreviewResult {
  source: string;
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
  info?: string;
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
