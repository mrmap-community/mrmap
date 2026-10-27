import type L from "leaflet";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslate } from 'react-admin';
import { ImageOverlay, ImageOverlayProps } from "react-leaflet";

import { useQuery } from "@tanstack/react-query";

import { OptimizedUrlsMap } from "../../ows-lib/OwsContext/core";
import { useMapViewerBase } from "../MapViewer/MapViewerBase";

export interface AuthOptions {
  headers?: Record<string, string>;
  credentials?: RequestCredentials;
}

export interface AuthImageOverlayProps extends Partial<ImageOverlayProps> {
  bounds: L.LatLngBounds;
  optimiuedUrl: OptimizedUrlsMap;
  interactive?: boolean;
  authenticationError?: string;
  auth?: AuthOptions | (() => AuthOptions) | Headers;
}

/**
 * Converts Headers object to Record<string, string>
 */
const headersToObject = (headers?: Headers): Record<string, string> => {
  if (!headers) return {};
  const obj: Record<string, string> = {};
  headers.forEach((value, key) => {
    obj[key] = value;
  });
  return obj;
};

/**
 * Gets authentication options. Supports:
 * 1. Explicit auth object
 * 2. Auth function that returns auth options
 * 3. Headers object that gets converted to auth options
 */
const getAuthOptions = (
  auth?: AuthOptions | (() => AuthOptions) | Headers,
): AuthOptions => {
  // If auth is a function, call it
  if (typeof auth === "function") {
    return auth();
  }

  // If auth is a Headers object, convert it
  if (auth instanceof Headers) {
    return {
      headers: headersToObject(auth),
    };
  }

  // If auth is an object, return it
  if (auth) {
    return auth;
  }
  return {};
};

const getServiceExceptionMessage = (xml: string): string | undefined => {
  if (!xml.trimStart().startsWith("<")) return undefined;

  try {
    const document = new DOMParser().parseFromString(xml, "application/xml");
    const exception = Array.from(document.getElementsByTagName("*")).find(
      (element) => element.localName === "ServiceException",
    );

    if (!exception) return undefined;

    const code = exception.getAttribute("code");
    const message = exception.textContent?.trim();

    if (code && message) return `${code}: ${message}`;
    return message || code || "OGC service exception";
  } catch {
    return undefined;
  }
};

export const AuthImageOverlay = ({
  bounds,
  optimiuedUrl,
  interactive = true,
  auth,
  authenticationError,
  opacity = 1,
  ...rest
}: AuthImageOverlayProps) => {
  const translate = useTranslate();
  const { reportMapLoading, removeMapLoading } = useMapViewerBase();
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const startedAt = useRef(performance.now());
  const overlay = useRef<L.ImageOverlay>(null);

  const authOptions = useMemo(() => getAuthOptions(auth), [auth]);
  const url = optimiuedUrl.url.href;

  // an endpoint of another origin which asks for no credentials at all is answered by the
  // browser straight from its url: an image needs no cross-origin permission to be shown,
  // while a fetched blob does - credentials keep their origin check through the fetched path.
  // The price is that a service exception which the remote labels as an image is only known
  // as a picture which did not load, because its body may not be read across the origin
  const direct =
    !authenticationError &&
    !authOptions.headers &&
    !authOptions.credentials &&
    new URL(url).origin !== window.location.origin;

  const loadingId = `image:${url}`;

  const { data, isFetching, error } = useQuery({
    queryKey: [
      "remoteImage",
      url,
      authOptions.headers,
      authOptions.credentials,
      authenticationError,
    ],
    enabled: !direct,
    gcTime: 0,
    retry: false,
    retryOnMount: false,
    queryFn: async ({ signal }) => {
      if (authenticationError) throw new Error(translate(`viewerAuth.${authenticationError}`));
      const response = await fetch(url, {
        redirect: authOptions.headers ? 'error' : 'follow',
        ...(authOptions.headers && { credentials: 'omit' }),
        signal,
        ...(authOptions.headers && { headers: authOptions.headers }),
        ...(authOptions.credentials && {
          credentials: authOptions.credentials,
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const blob = await response.blob();
      // WMS servers can label XML errors as images. Sniff a bounded prefix even
      // for image content types, and decode the full body only when it may be XML.
      const prefix = (await blob.slice(0, 512).text()).trimStart();
      const mayBeXml =
        blob.type.includes("xml") || prefix.startsWith("<") || prefix === "";
      const serviceExceptionMessage = mayBeXml
        ? getServiceExceptionMessage(await blob.text())
        : undefined;
      if (serviceExceptionMessage) {
        throw new Error(serviceExceptionMessage);
      }

      return blob;
    },
  });

  useEffect(() => {
    const timing = performance.now() - startedAt.current;
    if (isFetching) {
      reportMapLoading(loadingId, "loading");
    } else if (error) {
      const mapError = {
        message: error instanceof Error ? error.message : String(error),
        features: optimiuedUrl.features,
      };
      reportMapLoading(loadingId, "error", mapError, timing);
    } else if (data) {
      reportMapLoading(loadingId, "ready", undefined, timing);
    }
  }, [data, error, isFetching, loadingId, reportMapLoading]);

  useEffect(() => {
    return () => removeMapLoading(loadingId);
  }, [loadingId, removeMapLoading]);

  useEffect(() => {
    if (!data) {
      setImageUrl(null);
      return;
    }

    const nextImageUrl = URL.createObjectURL(data);
    setImageUrl(nextImageUrl);

    return () => {
      URL.revokeObjectURL(nextImageUrl);
    };
  }, [data]);

  // an overlay keeps the options it was created with, so the opacity a user blends a layer to is
  // given to the overlay itself; the image of the layer stays loaded for it (#750)
  useEffect(() => {
    overlay.current?.setOpacity(opacity);
  }, [opacity, imageUrl]);

  if (direct) {
    return (
      <ImageOverlay
        ref={overlay}
        bounds={bounds}
        url={url}
        interactive={interactive}
        opacity={opacity}
        eventHandlers={{
          load: () =>
            reportMapLoading(
              loadingId,
              "ready",
              undefined,
              performance.now() - startedAt.current,
            ),
          error: () =>
            reportMapLoading(
              loadingId,
              "error",
              {
                message: translate("viewerMap.imageFailed"),
                features: optimiuedUrl.features,
              },
              performance.now() - startedAt.current,
            ),
        }}
        {...rest}
      />
    );
  }

  if (error) {
    return null;
  }

  if (isFetching || !imageUrl) {
    return null;
  }

  return (
    <ImageOverlay
      ref={overlay}
      bounds={bounds}
      url={imageUrl}
      interactive={interactive}
      opacity={opacity}
      {...rest}
    />
  );
};
