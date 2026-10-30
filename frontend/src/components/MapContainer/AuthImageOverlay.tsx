import type L from "leaflet";

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslate } from 'react-admin';
import { ImageOverlay, ImageOverlayProps } from "react-leaflet";

import { useQuery } from "@tanstack/react-query";

import { OptimizedUrlsMap } from "../../ows-lib/OwsContext/core";
import { getOfferingTimeValue } from "../../ows-lib/OwsContext/dimensions";
import { useMapViewerBase } from "../MapViewer/MapViewerBase";
import {
  AuthOptions,
  getAuthOptions,
  remoteImageQuery,
} from "./remoteImage";
import { useTimeFrameBuffer } from "./useTimeFrameBuffer";

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
  // the observation this image answers for, read under the parameter the layer's time dimension was
  // selected with — the well known TIME or a DIM_<name> the timeline of the layer writes
  const time = getOfferingTimeValue(optimiuedUrl.url, optimiuedUrl.features[0]?.getWmsOffering());
  const folder = optimiuedUrl.features[0]?.properties.folder;

  const loadingId = `image:${url}`;

  // the image of the selected time, asked for through the same definition the buffering of its
  // neighbouring frames uses: a frame which is already in the buffer answers the selection without a
  // second request (#705)
  const { data, isFetching, error } = useQuery(
    remoteImageQuery(url, authOptions, translate, authenticationError),
  );

  // the frames around this selection are fetched ahead into the same cache, so that scrubbing and
  // playback reach the next observation without waiting for it (#705)
  useTimeFrameBuffer({
    url: optimiuedUrl.url,
    features: optimiuedUrl.features,
    authOptions,
    authenticationError,
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
  // is, for as long as this overlay draws it and for no longer; the server default image carries
  // no time parameter, so it reports the empty string rather than nothing, which is the answer
  // for "no image drawn" (#705)
  useEffect(() => {
    if (folder === undefined) return;
    setDisplayedTime(folder, displayed === undefined ? undefined : displayed.time ?? "");
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
