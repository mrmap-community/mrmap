import type L from "leaflet";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslate } from 'react-admin';
import { ImageOverlay, ImageOverlayProps } from "react-leaflet";

import { useQuery } from "@tanstack/react-query";

import { OptimizedUrlsMap } from "../../ows-lib/OwsContext/core";
import { getTimeParameter } from "../../ows-lib/OwsContext/dimensions";
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
 * An image drawn on the map: the object URL it was given, the request whose answer it is and the
 * time that answer was fetched for. The frame stays displayed until a successor has been fetched
 * and decoded, so it keeps answering which observation the map shows (#705).
 */
interface DisplayedFrame {
  href: string;
  objectUrl: string;
  time?: string;
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
  const { reportMapLoading, removeMapLoading, setDisplayedTime } = useMapViewerBase();
  const overlay = useRef<L.ImageOverlay>(null);

  const authOptions = useMemo(() => getAuthOptions(auth), [auth]);
  const url = optimiuedUrl.url.href;
  const time = getTimeParameter(optimiuedUrl.url);
  const folder = optimiuedUrl.features[0]?.properties.folder;

  const loadingId = `image:${url}`;

  const { data, isFetching, error } = useQuery({
    queryKey: [
      "remoteImage",
      url,
      authOptions.headers,
      authOptions.credentials,
      authenticationError,
    ],
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

  // the image which is drawn, kept while a new time frame is requested: swapping only once the
  // successor has been fetched and decoded answers a selection without the blank interval a
  // remount produces, and a slow or failed frame simply leaves the previous observation visible
  const [displayed, setDisplayed] = useState<DisplayedFrame>();
  const displayedRef = useRef<DisplayedFrame | undefined>(undefined);
  const [undecodable, setUndecodable] = useState<string>();
  const startedAt = useRef({ href: url, at: performance.now() });
  if (startedAt.current.href !== url) {
    startedAt.current = { href: url, at: performance.now() };
  }

  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    const objectUrl = URL.createObjectURL(data);
    const display = () => {
      if (cancelled) {
        // a newer selection or an unmount invalidated this frame while it was prepared
        URL.revokeObjectURL(objectUrl);
        return;
      }
      setUndecodable(undefined);
      const frame = { href: url, objectUrl, time };
      // the replaced frame leaves the map, so its object URL is released with it
      if (displayedRef.current && displayedRef.current.objectUrl !== objectUrl) {
        URL.revokeObjectURL(displayedRef.current.objectUrl);
      }
      displayedRef.current = frame;
      setDisplayed(frame);
    };
    const image = new Image();
    image.src = objectUrl;
    // let the browser decode the image before the overlay takes it, so that the swap cannot blank
    // while decoding; browsers without Image.decode draw the fetched image directly
    const decoding = (image as HTMLImageElement & { decode?: () => Promise<void> }).decode?.();
    if (decoding === undefined) {
      display();
      return () => {
        cancelled = true;
      };
    }
    decoding.then(display, () => {
      URL.revokeObjectURL(objectUrl);
      if (!cancelled) setUndecodable("undecodable");
    });
    return () => {
      cancelled = true;
    };
  }, [data, url, time]);

  useEffect(() => {
    const timing = performance.now() - startedAt.current.at;
    if (isFetching) {
      reportMapLoading(loadingId, "loading");
    } else if (error) {
      const mapError = {
        message: error instanceof Error ? error.message : String(error),
        features: optimiuedUrl.features,
      };
      reportMapLoading(loadingId, "error", mapError, timing);
    } else if (undecodable) {
      reportMapLoading(loadingId, "error", {
        message: translate("viewerMap.undecodable"),
        features: optimiuedUrl.features,
      }, timing);
    } else if (data) {
      reportMapLoading(loadingId, "ready", undefined, timing);
    }
  }, [data, error, undecodable, isFetching, loadingId, optimiuedUrl.features, reportMapLoading, translate]);

  useEffect(() => {
    return () => removeMapLoading(loadingId);
  }, [loadingId, removeMapLoading]);

  // the drawn frame answers a specific observation: tell the controls and identify which one it
  // is, for as long as this overlay draws it and for no longer (#705)
  useEffect(() => {
    if (folder === undefined) return;
    setDisplayedTime(folder, displayed?.time);
    return () => setDisplayedTime(folder, undefined);
  }, [folder, displayed, setDisplayedTime]);

  // an overlay keeps the options it was created with, so the opacity a user blends a layer to is
  // given to the overlay itself; the image of the layer stays loaded for it (#750)
  useEffect(() => {
    overlay.current?.setOpacity(opacity);
  }, [opacity, displayed]);

  // what is drawn is only released when the overlay itself leaves the map
  useEffect(() => () => {
    if (displayedRef.current) {
      URL.revokeObjectURL(displayedRef.current.objectUrl);
    }
  }, []);

  if (!displayed) {
    return null;
  }

  return (
    <ImageOverlay
      ref={overlay}
      bounds={bounds}
      url={displayed.objectUrl}
      interactive={interactive}
      opacity={opacity}
      {...rest}
    />
  );
};
