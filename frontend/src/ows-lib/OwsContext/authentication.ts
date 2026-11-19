import type { Authentication } from "./types";

import { v4 as uuidv4 } from "uuid";

import { HeaderAuthentication } from "./contrib";
import { OWSContext, Operation } from "./types";

/** An assignment never authorizes a different origin, including redirects. */
export const resolveOperationAuthentication = (
  context: OWSContext,
  operation: Operation,
  href = operation.href,
): { headers?: Headers; error?: string } => {
  const id = operation["x-authentication-id"];
  if (id === undefined) return {};
  const auth = Array.isArray(context.authenticationHeaders)
    ? context.authenticationHeaders.find((entry) => entry?.id === id)
    : undefined;
  if (!auth?.value) return { error: "missing" };
  try {
    const url = new URL(href);
    if (!["http:", "https:"].includes(url.protocol) || auth.type !== "header")
      return { error: "invalid" };
    const origin = url.origin;
    if (
      !auth.origin ||
      origin !== auth.origin ||
      new URL(operation.href).origin !== origin
    )
      return { error: "blocked" };
    return { headers: new Headers({ [auth.name]: auth.value }) };
  } catch {
    return { error: "invalid" };
  }
};

/** Credentials entered for capabilities apply only to this newly added service's origin. */
export const assignServiceAuthentication = (
  context: OWSContext,
  treeId: number,
  href: string,
  headers?: Headers,
) => {
  if (!headers || Array.from(headers).length === 0) return;
  const origin = new URL(href).origin;
  // Header credentials are represented individually; an operation uses one header assignment.
  const entries = Array.from(headers);
  if (entries.length !== 1)
    throw new Error("Configure one authentication header per operation");
  const [name, value] = entries[0];
  const auth: HeaderAuthentication = {
    id: uuidv4(),
    type: "header",
    name,
    value,
    origin,
  };
  context.authenticationHeaders = [
    ...(context.authenticationHeaders ?? []),
    auth,
  ];
  for (const feature of context.features) {
    if (
      !feature.properties.folder?.startsWith(`/${treeId}/`) &&
      feature.properties.folder !== `/${treeId}`
    )
      continue;
    for (const offering of feature.properties.offerings ?? []) {
      for (const operation of offering.operations ?? []) {
        // Cross-origin advertised endpoints require an explicit assignment in the editor.
        operation["x-authentication-id"] =
          new URL(operation.href).origin === origin
            ? auth.id
            : `missing:${auth.id}`;
      }
    }
  }
};

/**
 * Asks the operations of another origin than the document anonymously.
 *
 * The assignment above marks an operation of a foreign origin as `missing:` the credentials it read
 * for the document, because a header never authorizes a different origin, and the editor of the
 * viewer offers those operations to assign credentials of their own to them. A document which the
 * registry itself serves is the exception: it advertises the operations of a service it does not
 * secure at their upstream origin, where the session of the requester is neither expected nor
 * understood. A `missing:` assignment there fails the request on missing credentials, while no
 * assignment at all asks that service the way any other client of it would. Only the tree the
 * document brought in is looked at, and only a placeholder of the credentials the service was added
 * with is dropped - an operation which its user assigned credentials to keeps them.
 */
export const dropUnassignedAuthentication = (
  context: OWSContext,
  treeId: number,
  href: string,
) => {
  const origin = new URL(href).origin;
  for (const feature of context.features) {
    if (
      !feature.properties.folder?.startsWith(`/${treeId}/`) &&
      feature.properties.folder !== `/${treeId}`
    )
      continue;
    for (const offering of feature.properties.offerings ?? []) {
      for (const operation of offering.operations ?? []) {
        const assigned = operation["x-authentication-id"];
        if (
          typeof assigned === "string" &&
          assigned.startsWith("missing:") &&
          new URL(operation.href).origin !== origin
        )
          delete operation["x-authentication-id"];
      }
    }
  }
};

/** Copyable documents retain assignments but never credential values. */
export const serializeOwsContext = (context: OWSContext): string =>
  JSON.stringify(
    context,
    (key, value) => {
      if (key === "folderToResource") return undefined;
      if (key === "authenticationHeaders" && Array.isArray(value))
        return value.map(
          ({ value: _secret, ...entry }: HeaderAuthentication) => ({
            ...entry,
            value: "",
          }),
        );
      if (key === "authentications" && Array.isArray(value))
        return value.map(
          ({ username: _username, password: _password, value: _secret, ...entry }) => ({
            ...entry,
            username: "",
            password: "",
            ...(_secret !== undefined && { value: "" }),
          }),
        );
      return value;
    },
    2,
  );

/** a capabilities url without the request parameters which ride along with it */
const canonicalCapabilitiesUrl = (href: string): string => {
  const url = new URL(href);
  const keys = [...url.searchParams.keys()] // snapshot: the loop deletes entries, the live iterator would skip
  for (const key of keys) {
    if (["SERVICE", "REQUEST", "VERSION"].includes(key.toUpperCase()))
      url.searchParams.delete(key);
  }
  url.searchParams.sort();
  return url.href;
};

/** the operations a feature's offerings advertise */
const featureOperations = (feature: OWSContext["features"][number]): Operation[] =>
  feature.properties.offerings?.flatMap(
    (offering) => offering.operations ?? [],
  ) ?? [];

/** whether one of the operations is the GetCapabilities the legacy entry was written for */
const answersGetCapabilities = (operations: Operation[], legacyUrl: string): boolean =>
  operations.some(
    (operation) =>
      operation.code === "GetCapabilities" &&
      canonicalCapabilitiesUrl(operation.href) ===
        canonicalCapabilitiesUrl(legacyUrl),
  );

/** stamps every operation which carries no authentication yet: same-origin ones
 *  directly, the others as missing, which keeps them unauthorized for the viewer */
const stampOperations = (operations: Operation[], authId: string, origin: string): void => {
  for (const operation of operations) {
    if (operation["x-authentication-id"] === undefined)
      operation["x-authentication-id"] =
        new URL(operation.href).origin === origin ? authId : `missing:${authId}`;
  }
};

/** whether a legacy entry states all three parts of Basic auth as text */
const isUsableLegacyEntry = (legacy: Authentication): boolean =>
  Boolean(legacy) &&
  typeof legacy.getCapabilitiesUrl === "string" &&
  typeof legacy.username === "string" &&
  typeof legacy.password === "string";

/** the header entry a usable legacy entry turns into, after stamping the
 *  operations it answers; undefined when the entry must not authorize anything */
const migrateLegacyEntry = (context: OWSContext, legacy: Authentication): HeaderAuthentication | undefined => {
  try {
    const origin = new URL(legacy.getCapabilitiesUrl).origin;
    const auth: HeaderAuthentication = {
      id: uuidv4(),
      type: "header",
      name: "Authorization",
      value: legacy.username && legacy.password ? `Basic ${btoa(legacy.username + ":" + legacy.password)}` : "",
      origin,
    };
    for (const feature of context.features) {
      const operations = featureOperations(feature);
      if (!answersGetCapabilities(operations, legacy.getCapabilitiesUrl)) continue;
      stampOperations(operations, auth.id, origin);
    }
    return auth;
  } catch {
    /* Malformed legacy credentials must never authorize an operation. */
    return undefined;
  }
};

/** Read the former capabilities-only Basic-auth entries without widening their service scope. */
export const migrateLegacyAuthentications = (context: OWSContext) => {
  const legacyEntries = Array.isArray(context.authentications) ? context.authentications : [];
  const migrated = new Set<(typeof legacyEntries)[number]>();
  for (const legacy of legacyEntries) {
    if (!isUsableLegacyEntry(legacy)) continue;
    const auth = migrateLegacyEntry(context, legacy);
    if (auth === undefined) continue;
    context.authenticationHeaders = [...(context.authenticationHeaders ?? []), auth];
    migrated.add(legacy);
  }
  if (migrated.size > 0) {
    context.authentications = legacyEntries.filter(entry => !migrated.has(entry));
    if (context.authentications.length === 0) delete context.authentications;
  }
};
