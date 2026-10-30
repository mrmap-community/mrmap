import type { OWSResource } from "../../ows-lib/OwsContext/core";

import { useEffect, useMemo, useRef } from "react";
import { useTranslate } from "react-admin";

import { useQueryClient } from "@tanstack/react-query";

import { getSteppedTimeDimension, getUpcomingTimeAxisPositions, getTimeValueOfDimension, writeTimeForDimension } from "../../ows-lib/OwsContext/dimensions";
import { useOwsContextBase } from "../../react-ows-lib/ContextProvider/OwsContextBase";
import { useMapViewerBase } from "../MapViewer/MapViewerBase";
import { AuthOptions, remoteImageIdentity, remoteImageKey, remoteImageQuery, RemoteImageKey } from "./remoteImage";

/** Frames buffered ahead of the selection while the viewer is scrubbing by hand. */
const AHEAD = 3;
/** One frame behind the selection, which is what scrubbing back reaches for before the next step. */
const BEHIND = 1;
/** Buffered frames on their way at once; the request an overlay waits for itself comes on top of these. */
const PARALLEL = 2;
/** Seconds of animation the buffering tries to keep fetched ahead of the frame being drawn. */
const RUNWAY_SECONDS = 4;
/** How far ahead of a playing selection at most — frames cost memory; the workers bound the network. */
const AHEAD_PLAYING = 12;

export interface TimeFrameBufferProps {
  /** the GetMap request whose frames are buffered; it carries the selected time */
  url: URL;
  /** the layers the request draws — only what they advertise can be buffered */
  features: OWSResource[];
  /** the authentication the images of this request are fetched with, which their frames belong to */
  authOptions: AuthOptions;
  authenticationError?: string;
}

/**
 * Keeps the frames around the selected time of a map request at hand, so that scrubbing and playback
 * reach an observation which is already fetched instead of waiting for one: the images of the neighbouring
 * frames are asked for through the key an overlay draws them under, and a selection which arrives at a
 * buffered frame is answered from it without a second request (#705).
 *
 * The buffer is deliberately small and belongs to one map request. Only the advertised neighbours of the
 * selection are asked for, at most two of them at a time, and every frame the selection moves away from
 * is taken back — which aborts a request still on its way and releases the image of one which arrived. A
 * frame the service refuses is left out, so asking its time again asks the service again.
 */
export const useTimeFrameBuffer = ({
  url,
  features,
  authOptions,
  authenticationError,
}: TimeFrameBufferProps): void => {
  const queryClient = useQueryClient();
  const translate = useTranslate();
  const { owsContext } = useOwsContextBase();
  const { animation, timelines } = useMapViewerBase();

  const href = url.href;

  // the observations which follow this selection, taken from the advertised axis of the layer whose
  // timeline the viewer works with: playback advances that layer and the other layers of a shared image
  // follow its time. A time the axis does not carry has no advertised neighbour and the server default has
  // no position at all, so nothing is invented for either (#705).
  const upcoming = useMemo(() => {
    if (authenticationError !== undefined) return [];
    const request = new URL(href);
    const candidates = [animation?.folder, ...features.map(feature => feature.properties.folder)]
      .filter((folder, position, all): folder is string =>
        folder !== undefined && all.indexOf(folder) === position);
    for (const folder of candidates) {
      // a layer whose timeline is open somewhere in the viewer is the one its frames are buffered for: the
      // frames of a layer nobody works with would be asked for on every pan and never reached for (#705)
      if ((timelines?.[folder] ?? 0) <= 0 && animation?.folder !== folder) continue;
      const offering = owsContext.findResourceByFolder(folder)?.getWmsOffering();
      const stepped = getSteppedTimeDimension(offering);
      if (stepped === undefined) continue;
      // the observation this request asks for, read from the parameter the dimension was selected
      // with — the well known TIME or a DIM_<name> — which is also the parameter the frames are asked under
      const time = getTimeValueOfDimension(request.searchParams, stepped.dimension.name);
      const position = time === undefined ? -1 : stepped.axis.indexOf(time);
      if (position < 0) continue;
      // an animation only ever walks onwards, so a frame behind is only worth fetching while paused;
      // while it plays the window grows to a runway of seconds worth of frames, so that the steps of
      // the animation are drawn from the buffer rather than each waiting for its own request (#823)
      const advancing = animation?.folder === folder ? animation : undefined;
      const ahead = advancing === undefined
        ? AHEAD
        : Math.min(AHEAD_PLAYING, Math.max(AHEAD, Math.ceil(advancing.fps * RUNWAY_SECONDS)));
      return getUpcomingTimeAxisPositions(stepped.axis, position, {
        ahead,
        behind: advancing ? 0 : BEHIND,
        loop: advancing?.loop ?? false,
      }).map(next => {
        const frame = new URL(href);
        // the time is replaced in its position, so the frame carries the very url the overlay will
        // draw it under — a buffered frame only answers a selection when both are one identical key
        writeTimeForDimension(frame.searchParams, stepped.dimension.name, stepped.axis.valueAt(next));
        return frame.href;
      });
    }
    return [];
  }, [animation, authenticationError, features, href, owsContext, timelines]);

  // every frame this overlay asked for, so the ones nobody wants anymore can be taken back; the frame the
  // overlay draws itself belongs to them, because it is released with it
  const frames = useRef(new Map<string, RemoteImageKey>());
  const generation = useRef(0);
  const released = useRef(false);

  useEffect(() => {
    released.current = false;
    const running = ++generation.current; // every newer selection takes the buffer over
    const keyOf = (frame: string) => remoteImageKey(frame, authOptions, authenticationError);
    const asked = (frame: string) => remoteImageQuery(frame, authOptions, translate, authenticationError);
    const wanted = new Set([href, ...upcoming].map(frame => remoteImageIdentity(keyOf(frame))));
    frames.current.set(remoteImageIdentity(keyOf(href)), keyOf(href));
    for (const [frame, key] of frames.current) {
      if (wanted.has(frame)) continue;
      frames.current.delete(frame);
      // taking a frame back aborts its request while it is on its way and releases the image of one which
      // arrived, so buffering cannot grow with the length of the advertised range (#705)
      queryClient.removeQueries({ queryKey: key });
    }
    const buffer = async (frame: string) => {
      const key = keyOf(frame);
      const identity = remoteImageIdentity(key);
      frames.current.set(identity, key);
      try {
        await queryClient.fetchQuery(asked(frame));
      } catch {
        // a frame the service refuses is no buffer: asking its time again must ask the service again
        queryClient.removeQueries({ queryKey: key });
      }
      // a frame which came back after a newer selection, or after the overlay itself, took it out of the
      // buffer answers an image nobody draws anymore
      if (!frames.current.has(identity)) queryClient.removeQueries({ queryKey: key });
    };
    // the frames are fetched by two workers which take the next one as soon as one of them is done, so the
    // bound holds without a slow frame holding up the ones behind it; a worker stops as soon as its
    // selection is not the current one anymore
    const queue = [...upcoming];
    const worker = async (): Promise<void> => {
      const frame = queue.shift();
      if (frame === undefined || released.current || generation.current !== running) return;
      await buffer(frame);
      return worker();
    };
    void Promise.allSettled(
      Array.from({ length: Math.min(PARALLEL, queue.length) }, worker),
    );
  }, [authenticationError, authOptions, href, queryClient, translate, upcoming]);

  // what was buffered for one request is asked for no more once its overlay leaves the map, which is also
  // how a change of viewport, size, CRS, style, other dimensions, layer or authentication lets go of the
  // frames it made obsolete: they answer an image no overlay draws under that identity anymore (#705)
  useEffect(() => () => {
    released.current = true;
    for (const [, key] of frames.current) queryClient.removeQueries({ queryKey: key });
    frames.current.clear();
  }, [queryClient]);
};
