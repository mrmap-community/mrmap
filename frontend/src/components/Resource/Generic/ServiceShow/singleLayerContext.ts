import type { OWSResource } from "../../../../ows-lib/OwsContext/core";

import type { RaRecord } from "react-admin";

import { API_BASE_URL } from "../../../../context/HttpClientContext";
import { getUnsupportedReasons, type UnsupportedReason } from "../../../../ows-lib/OwsContext/capabilities";
import { OWSContext } from "../../../../ows-lib/OwsContext/core";
import { getAuthToken } from "../../../../providers/authProvider";
import { validExtent } from "../../../MapViewer/utils";

/**
 * The capabilities document which advertises exactly one layer or feature type. The api names it on
 * the element itself and the document is generated out of the registry for every request, so it
 * answers the current state of the element and nothing beside it.
 *
 * A secured service answers this document camouflaged (registry/models/document.py): the operations
 * it advertises point back to this origin, which is the mrmap security proxy. A viewer seeded with
 * it therefore asks the proxy, which authenticates upstream with the stored credentials of the
 * service and applies the spatial rules of the requesting user; the browser never learns them.
 */
/** An element names its document as an absolute url or as a path of this deployment. */
const isDocumentUrl = (value: string): boolean => {
  if (value.startsWith("/")) return true;
  try {
    return ["http:", "https:"].includes(new URL(value).protocol);
  } catch {
    return false;
  }
};

export const elementCapabilitiesUrl = (element?: RaRecord): URL | undefined => {
  const url = element?.capabilitiesUrl;
  if (typeof url !== "string" || !isDocumentUrl(url)) return undefined;
  try {
    // the api answers an absolute url, a deployment answering a relative one still means itself
    return new URL(url, API_BASE_URL);
  } catch {
    return undefined;
  }
};

/**
 * The header which identifies the session at the proxy, or undefined when nobody is signed in. The
 * provider keeps it as an authentication of the capabilities url's origin only, so it never travels
 * to an operation advertised on another origin.
 */
export const sessionHeader = (): Headers | undefined => {
  const token = getAuthToken()?.token;
  return token ? new Headers({ Authorization: `Token ${token}` }) : undefined;
};

/** The resources of the tree the appended document brought in, the service root included. */
const ofTree = (feature: OWSResource, treeId: number): boolean => {
  const folder = feature.properties.folder;
  if (folder === undefined) return false;
  const root = `/${treeId}`;
  return folder === root || folder.startsWith(`${root}/`);
};

/** A group node asks for nothing of its own; only the resources below it are rendered. */
const isResource = (feature: OWSResource): boolean => feature.children.length === 0;

/** The first of the given resources which answers a usable extent. */
const advertisedOf = (resources: OWSResource[]): number[] | undefined =>
  resources.map((feature) => feature.bbox).find(validExtent);

/**
 * The extent the element which is active in the document advertises, or undefined when neither it
 * nor any other active resource answers one. It is the area the preview of an element zooms to,
 * because it is the one the service will answer a request for that element with.
 */
export const advertisedExtent = (context: OWSContext): number[] | undefined =>
  advertisedOf(context.getActiveFeatures());

/**
 * The activation and the area of interest of exactly one element.
 *
 * A layer or feature type which arrives with a capabilities document is not active: the request
 * building of the viewer asks the *operation* whether it shall be asked, so both are set here and
 * nothing else of the document is touched. The area of interest of the document becomes the extent
 * the element advertises, which is what the map of the preview is zoomed to.
 */
export const activateElement =
  (extent?: number[]) =>
  (context: OWSContext, treeId: number): OWSContext => {
    const resources = context.features.filter(
      (feature) => ofTree(feature, treeId) && isResource(feature),
    );
    resources.forEach((feature) => {
      feature.properties.active = true;
      feature.properties.offerings?.forEach((offering) =>
        offering.operations?.forEach((operation) => {
          operation.active = true;
        }),
      );
    });

    // the extent the element advertises outranks the one stored in the registry
    const area = advertisedOf(resources) ?? extent;
    if (validExtent(area)) {
      context.bbox = [...area] as [number, number, number, number];
    }
    return context;
  };

/**
 * Why the element of the context cannot be rendered here, empty when it can. An offering which is
 * not WMS or WFS, an operation offered as POST, a feature type without a GeoJSON answer or without
 * a WGS 84 crs all answer a reason the caller shows instead of an empty map.
 */
export const unsupportedOf = (context: OWSContext): UnsupportedReason[] => {
  const active = context.getActiveFeatures();
  if (active.length === 0) return [];
  return active
    .filter((feature) => isResource(feature))
    .flatMap((feature) => getUnsupportedReasons(feature));
};
