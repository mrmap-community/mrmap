import { describe, expect, it } from "vitest";

import {
  assignServiceAuthentication,
  dropUnassignedAuthentication,
  resolveOperationAuthentication,
  serializeOwsContext,
} from "./authentication";
import { OWSContext, OWSResource } from "./core";
import { Operation } from "./types";
import { validateOwsContext } from "./validation";

const operation = (origin = "https://protected.example"): Operation => ({
  code: "GetMap",
  method: "GET",
  href: `${origin}/wms`,
  active: true,
});
const resource = (folder: string, operations: Operation[]) =>
  new OWSResource({
    title: folder,
    folder,
    updated: new Date().toISOString(),
    offerings: [{ code: "wms", operations }],
  });
const setup = () => {
  const context = new OWSContext(undefined, [
    resource("/0", [operation(), operation("https://other.example")]),
    resource("/1", [operation()]),
  ]);
  assignServiceAuthentication(
    context,
    0,
    "https://protected.example/wms",
    new Headers({ Authorization: "Basic secret" }),
  );
  return context;
};
const operations = (context: OWSContext) =>
  context.features.flatMap((feature) =>
    feature.properties.offerings!.flatMap((offering) => offering.operations!),
  );

describe("operation credentials", () => {
  it("assigns only the added tree, and authorizes only its configured origin", () => {
    const context = setup();
    const [sameOrigin, otherOrigin, otherService] = operations(context);
    expect(
      resolveOperationAuthentication(context, sameOrigin).headers?.get(
        "Authorization",
      ),
    ).toBe("Basic secret");
    expect(resolveOperationAuthentication(context, otherOrigin).error).toBe(
      "missing",
    );
    expect(resolveOperationAuthentication(context, otherService)).toEqual({});
    expect(
      resolveOperationAuthentication(
        context,
        sameOrigin,
        "https://unrelated.example/wms",
      ).error,
    ).toBe("blocked");
    otherOrigin["x-authentication-id"] = sameOrigin["x-authentication-id"];
    expect(resolveOperationAuthentication(context, otherOrigin).error).toBe(
      "blocked",
    );
  });
  it("blocks unresolved assignments and credentials without an explicit origin", () => {
    const context = setup();
    const op = operations(context)[0];
    context.authenticationHeaders![0].origin = undefined;
    expect(resolveOperationAuthentication(context, op).error).toBe("blocked");
    context.authenticationHeaders = [];
    expect(resolveOperationAuthentication(context, op).error).toBe("missing");
  });
  it("redacts exported secrets without losing assignments or mutating session credentials", () => {
    const context = setup();
    const document = serializeOwsContext(context);
    expect(document).not.toContain("Basic secret");
    expect(document).not.toContain("folderToResource");
    const imported = OWSContext.fromPlainObject(JSON.parse(document));
    expect(
      resolveOperationAuthentication(imported, operations(imported)[0]).error,
    ).toBe("missing");
    expect(
      resolveOperationAuthentication(
        context,
        operations(context)[0],
      ).headers?.get("Authorization"),
    ).toBe("Basic secret");
  });
  it("migrates capabilities-only credentials for the matching service and same-origin operations", () => {
    const context = new OWSContext(undefined, [
      resource("/0", [
        {
          ...operation(),
          code: "GetCapabilities",
          href: "https://protected.example/wms?SERVICE=WMS&REQUEST=GetCapabilities",
        },
        operation(),
        operation("https://other.example"),
      ]),
      resource("/1", [operation()]),
    ]);
    context.authentications = [
      {
        getCapabilitiesUrl: "https://protected.example/wms",
        username: "reader",
        password: "password",
      },
    ];
    const migrated = OWSContext.fromPlainObject(context);
    const [capabilities, map, other, unrelated] = operations(migrated);
    expect(
      resolveOperationAuthentication(migrated, capabilities).headers?.get(
        "Authorization",
      ),
    ).toBe(`Basic ${btoa("reader:password")}`);
    expect(resolveOperationAuthentication(migrated, map).headers).toBeDefined();
    expect(resolveOperationAuthentication(migrated, other).error).toBe(
      "missing",
    );
    expect(resolveOperationAuthentication(migrated, unrelated)).toEqual({});
  });
});

it.each(['GetMap', 'GetFeatureInfo'])('keeps %s request credentials isolated through batching', code => {
  const makeOperation = (layer: string, auth: string): Operation => ({
    code, method: 'GET', active: true,
    href: `https://protected.example/wms?SERVICE=WMS&REQUEST=${code}&VERSION=1.3.0&LAYERS=${layer}${code === 'GetFeatureInfo' ? `&QUERY_LAYERS=${layer}` : ''}`,
    'x-authentication-id': auth,
  });
  const context = new OWSContext(undefined, [
    resource('/0', []),
    resource('/0/0', [makeOperation('first', 'first')]),
    resource('/0/1', [makeOperation('second', 'second')]),
    resource('/0/2', [makeOperation('third', 'second')]),
  ]);
  for (const feature of context.features) feature.properties.offerings![0].code = 'http://www.opengis.net/spec/owc-geojson/1.0/req/wms';
  context.authenticationHeaders = ['first', 'second'].map(id => ({ id, type: 'header', origin: 'https://protected.example', name: 'Authorization', value: `Bearer ${id}` }));
  const batches = context.getOptimizedUrlsByCode(code, () => true);
  expect(batches).toHaveLength(2);
  expect(batches.map(batch => batch.url.searchParams.get('LAYERS'))).toEqual(['first', 'second,third']);
  expect(batches.map(batch => resolveOperationAuthentication(context, batch.operations[0], batch.url.href).headers?.get('Authorization'))).toEqual(['Bearer first', 'Bearer second']);
});

it.each([{}, [null], [{ id: 'a', type: 'header', name: 'Authorization', value: 123 }]])('rejects malformed authentication extensions without replacing the context', authenticationHeaders => {
  const context = new OWSContext();
  const document = { ...context, authenticationHeaders };
  const result = validateOwsContext(document);
  expect(result.hasErrors).toBe(true);
  expect(result.issues.some(issue => issue.path.startsWith('authenticationHeaders'))).toBe(true);
});


it('redacts header values held by older authentication extensions', () => {
  const context = new OWSContext();
  const legacy = { ...context, authentications: [{ type: 'header', name: 'Authorization', value: 'legacy-secret' }] };
  expect(serializeOwsContext(legacy as unknown as OWSContext)).not.toContain('legacy-secret');
});

it('asks an operation of another origin than the registry document anonymously', () => {
  const context = setup();
  dropUnassignedAuthentication(context, 0, 'https://protected.example/wms');
  const [sameOrigin, otherOrigin, otherService] = operations(context);
  // the operation the document serves itself keeps the credentials it was added with
  expect(resolveOperationAuthentication(context, sameOrigin).headers?.get('Authorization')).toBe('Basic secret');
  // the placeholder of the upstream operation is gone, so it is asked without the session
  expect(resolveOperationAuthentication(context, otherOrigin)).toEqual({});
  // a tree added beside this one keeps what it was assigned
  expect(resolveOperationAuthentication(context, otherService)).toEqual({});
});

it('keeps credentials a user assigned to an operation of another origin', () => {
  const context = setup();
  const [sameOrigin, otherOrigin] = operations(context);
  otherOrigin['x-authentication-id'] = sameOrigin['x-authentication-id'];
  dropUnassignedAuthentication(context, 0, 'https://protected.example/wms');
  expect(resolveOperationAuthentication(context, otherOrigin).error).toBe('blocked');
});
