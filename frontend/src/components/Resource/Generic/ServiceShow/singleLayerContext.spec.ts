import type { RaRecord } from "react-admin";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE_URL } from "../../../../context/HttpClientContext";
import { OWSContext, OWSResource } from "../../../../ows-lib/OwsContext/core";
import { WFS_OFFERING_CODE, WMS_OFFERING_CODE } from "../../../../ows-lib/OwsContext/validation";
import { activateElement, elementCapabilitiesUrl, sessionHeader, unsupportedOf } from "./singleLayerContext";

const authState = vi.hoisted(() => ({ token: undefined as string | undefined }));

vi.mock("../../../../providers/authProvider", () => ({
  getAuthToken: () => (authState.token === undefined ? null : { token: authState.token }),
}));

const wmsLeaf = (title: string, options: { bbox?: [number, number, number, number] } = {}) =>
  new OWSResource(
    {
      title,
      updated: "",
      offerings: [{
        code: WMS_OFFERING_CODE,
        operations: [{ code: "GetMap", method: "GET", href: `https://proxy.test/wms/layer/x?LAYERS=${title}` }],
      }],
    },
    title,
    options.bbox,
  );

const wfsLeafWithoutGeoJson = (title: string) =>
  new OWSResource(
    {
      title,
      updated: "",
      offerings: [{
        code: WFS_OFFERING_CODE,
        outputFormats: ["application/gml+xml; version=3.2"],
        defaultCrs: "EPSG:4326",
        operations: [{ code: "GetFeature", method: "GET", href: "https://proxy.test/wfs/featuretype/x" }],
      }],
    },
    title,
  );

const serviceRoot = (title = "service", children: OWSResource[] = []) =>
  new OWSResource({ title, updated: "" }, title, undefined, undefined, children);

/** The document of a viewer session, with the numbered folders the viewer works on. */
const contextOf = (...features: OWSResource[]) =>
  new OWSContext(undefined, features, undefined, {
    lang: "en",
    title: "preview",
    updated: new Date().toISOString(),
    display: {},
  });

/** The context keeps its own copies of the resources it was given. */
const of = (context: OWSContext, title: string): OWSResource =>
  context.features.find((feature) => feature.properties.title === title) as OWSResource;

/** The id a document is appended with names the first segment of the folder of its resources. */
const treeIdOf = (resource: OWSResource): number =>
  Number(resource.properties.folder?.split("/")[1]);

/** Every element the api answers carries an id; the tests below only vary the document it names. */
const element = (fields: Partial<RaRecord>): RaRecord => ({ id: "6b1", ...fields });

beforeEach(() => {
  authState.token = undefined;
});

describe("the capabilities document of one element", () => {
  it("answers the url the api names on the element", () => {
    const url = elementCapabilitiesUrl(element({ capabilitiesUrl: "https://mrmap.test/mrmap-proxy/wms/layer/6b1" }));
    expect(url?.href).toBe("https://mrmap.test/mrmap-proxy/wms/layer/6b1");
  });

  it("reads a path as a document of the api it was answered by", () => {
    const url = elementCapabilitiesUrl(element({ capabilitiesUrl: "/mrmap-proxy/wfs/featuretype/9c2" }));
    expect(url?.origin).toBe(API_BASE_URL);
    expect(url?.pathname).toBe("/mrmap-proxy/wfs/featuretype/9c2");
  });

  it("answers nothing when the element names no document or one which is not a url", () => {
    expect(elementCapabilitiesUrl(undefined)).toBeUndefined();
    expect(elementCapabilitiesUrl(element({}))).toBeUndefined();
    expect(elementCapabilitiesUrl(element({ capabilitiesUrl: "" }))).toBeUndefined();
    expect(elementCapabilitiesUrl(element({ capabilitiesUrl: "not a url" }))).toBeUndefined();
    expect(elementCapabilitiesUrl(element({ capabilitiesUrl: "file:///etc/passwd" }))).toBeUndefined();
  });
});

describe("the header the preview asks the proxy with", () => {
  it("carries the token of the session", () => {
    authState.token = "s3cret";
    expect(sessionHeader()?.get("Authorization")).toBe("Token s3cret");
  });

  it("asks anonymously when nobody is signed in", () => {
    expect(sessionHeader()).toBeUndefined();
  });
});

describe("activating exactly one element", () => {
  it("activates the resource of the appended tree with its operations", () => {
    const context = contextOf(serviceRoot("service", [wmsLeaf("rivers")]), wmsLeaf("rivers"));
    const layer = of(context, "rivers");

    activateElement()(context, treeIdOf(layer));

    expect(layer.properties.active).toBe(true);
    expect(layer.getWmsOperationByCode("GetMap")?.active).toBe(true);
  });

  it("leaves the group node inactive and everything of another tree alone", () => {
    const context = contextOf(
      serviceRoot("service", [wmsLeaf("rivers")]),
      wmsLeaf("rivers"),
      serviceRoot("other service", [wmsLeaf("lakes")]),
      wmsLeaf("lakes"),
    );
    const layer = of(context, "rivers");

    activateElement()(context, treeIdOf(layer));

    expect(of(context, "service").properties.active).toBeUndefined();
    expect(of(context, "lakes").properties.active).toBeUndefined();
    expect(of(context, "lakes").getWmsOperationByCode("GetMap")?.active).toBeUndefined();
  });

  it("zooms the map to the extent the element advertises", () => {
    const context = contextOf(wmsLeaf("rivers", { bbox: [6, 49, 12, 55] }));
    const layer = of(context, "rivers");

    activateElement([0, 40, 20, 60])(context, treeIdOf(layer));

    expect(context.bbox).toEqual([6, 49, 12, 55]);
  });

  it("keeps to the extent stored for the element when the document advertises none", () => {
    const context = contextOf(wmsLeaf("rivers"));
    const layer = of(context, "rivers");

    activateElement([0, 40, 20, 60])(context, treeIdOf(layer));

    expect(context.bbox).toEqual([0, 40, 20, 60]);
  });

  it("leaves the area of interest of the document alone when nothing answers an extent", () => {
    const context = contextOf(wmsLeaf("rivers"));
    const layer = of(context, "rivers");

    activateElement()(context, treeIdOf(layer));

    expect(context.bbox).toEqual([-180, -90, 180, 90]);
  });
});

describe("what the preview cannot render", () => {
  it("names nothing for a layer it can ask a map of", () => {
    const context = contextOf(wmsLeaf("rivers"));
    activateElement()(context, treeIdOf(of(context, "rivers")));

    expect(unsupportedOf(context)).toEqual([]);
  });

  it("names the answer a feature type is asked for which the viewer cannot draw", () => {
    const context = contextOf(wfsLeafWithoutGeoJson("roads"));
    activateElement()(context, treeIdOf(of(context, "roads")));

    expect(unsupportedOf(context)).toEqual([{ kind: "format", code: "GetFeature" }]);
  });

  it("names nothing while no element is active at all", () => {
    expect(unsupportedOf(contextOf(wfsLeafWithoutGeoJson("roads")))).toEqual([]);
  });
});
