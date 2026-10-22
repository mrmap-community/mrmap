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

/** Read the former capabilities-only Basic-auth entries without widening their service scope. */
export const migrateLegacyAuthentications = (context: OWSContext) => {
  const canonical = (href: string) => {
    const url = new URL(href);
    for (const key of [...url.searchParams.keys()]) {
      if (["SERVICE", "REQUEST", "VERSION"].includes(key.toUpperCase()))
        url.searchParams.delete(key);
    }
    url.searchParams.sort();
    return url.href;
  };
  const legacyEntries = Array.isArray(context.authentications) ? context.authentications : [];
  const migrated = new Set<(typeof legacyEntries)[number]>();
  for (const legacy of legacyEntries) {
    try {
      if (!legacy || typeof legacy.getCapabilitiesUrl !== "string" || typeof legacy.username !== "string" || typeof legacy.password !== "string") continue;
      const origin = new URL(legacy.getCapabilitiesUrl).origin;
      const auth: HeaderAuthentication = {
        id: uuidv4(),
        type: "header",
        name: "Authorization",
        value: legacy.username && legacy.password ? `Basic ${btoa(`${legacy.username}:${legacy.password}`)}` : "",
        origin,
      };
      context.authenticationHeaders = [
        ...(context.authenticationHeaders ?? []),
        auth,
      ];
      migrated.add(legacy);
      for (const feature of context.features) {
        const operations =
          feature.properties.offerings?.flatMap(
            (offering) => offering.operations ?? [],
          ) ?? [];
        if (
          !operations.some(
            (operation) =>
              operation.code === "GetCapabilities" &&
              canonical(operation.href) ===
                canonical(legacy.getCapabilitiesUrl),
          )
        )
          continue;
        for (const operation of operations) {
          if (operation["x-authentication-id"] === undefined)
            operation["x-authentication-id"] =
              new URL(operation.href).origin === origin
                ? auth.id
                : `missing:${auth.id}`;
        }
      }
    } catch {
      /* Malformed legacy credentials must never authorize an operation. */
    }
  }
  if (migrated.size > 0) {
    context.authentications = legacyEntries.filter(entry => !migrated.has(entry));
    if (context.authentications.length === 0) delete context.authentications;
  }
};
