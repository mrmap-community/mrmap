/**
 * Pins the resource-level access policy of #836 - the whole table behind
 * `authProvider.canAccess`, judged without react-admin:
 *
 * - administration resources need a snapshot with administration, which today
 *   means `who-am-i`'s `isSuperuser` and, once #736 names the builtin roles,
 *   a name from the administration table (specs inject the set);
 * - everything else stays as it is today: every logged-in user may reach it,
 *   the backend keeps enforcing the records;
 * - anonymous requests are denied while #833 has not chosen its public set;
 * - a record that carries #738's `allowedActions` is judged by that field
 *   alone - the policy never guesses a record permission it did not get.
 */
import { describe, expect, it } from "vitest";

import {
  ADMINISTRATION_RESOURCES,
  ADMINISTRATION_ROLES,
  ANONYMOUS_SNAPSHOT,
  PUBLIC_READ_RESOURCES,
  canAccessFromSnapshot,
  hasAdministration,
  permissionSnapshotFromWhoAmI,
  type PermissionSnapshot,
} from "./permissions";

const PLAIN: PermissionSnapshot = { roles: [], isSuperuser: false };
const SUPERUSER: PermissionSnapshot = { roles: [], isSuperuser: true };

/** The #736 shape is not fixed yet; the wiring test names one and injects it. */
const ORGANIZATION_ADMIN = new Set(["organization_admin"]);

const asAnonymous = (action: string, resource: string) =>
  canAccessFromSnapshot({
    action,
    resource,
    authenticated: false,
    snapshot: ANONYMOUS_SNAPSHOT,
  });

describe("who-am-i permission parsing", () => {
  it("reads the superuser flag the current who-am-i already camelizes", () => {
    expect(
      permissionSnapshotFromWhoAmI({
        data: { id: "1", attributes: { username: "ada", isSuperuser: true } },
      })
    ).toEqual({ roles: [], isSuperuser: true });
  });

  it("accepts the #736 roles as attribute names, as role objects, or as a relationship", () => {
    const roles = [{ name: "organization_admin" }, "platform_admin"];
    const withAttributes = permissionSnapshotFromWhoAmI({
      data: { attributes: { roles: ["a", { name: "b" }, { title: 1 }] } },
    });
    expect(withAttributes.roles).toEqual(["a", "b"]);

    const withRelationship = permissionSnapshotFromWhoAmI({
      data: { relationships: { roles: { data: roles } } },
    });
    expect(withRelationship.roles).toEqual(["organization_admin", "platform_admin"]);
  });

  it("answers the empty snapshot for a body that carries neither roles nor a flag", () => {
    expect(permissionSnapshotFromWhoAmI(undefined)).toEqual(ANONYMOUS_SNAPSHOT);
    expect(permissionSnapshotFromWhoAmI({ data: { attributes: {} } })).toEqual(
      ANONYMOUS_SNAPSHOT
    );
  });
});

describe("administration", () => {
  it("is answered by the superuser flag today", () => {
    expect(hasAdministration(SUPERUSER)).toBe(true);
    expect(hasAdministration(PLAIN)).toBe(false);
  });

  it("is answered by a #736 role name once the wiring table names it", () => {
    expect(
      hasAdministration(
        { roles: ["organization_admin"], isSuperuser: false },
        ORGANIZATION_ADMIN
      )
    ).toBe(true);
    expect(
      hasAdministration({ roles: ["editor"], isSuperuser: false }, ORGANIZATION_ADMIN)
    ).toBe(false);
  });

  it("carries the accounts and platform resources, plus #736's role resources", () => {
    for (const resource of ["User", "Organization", "SystemInfo", "Role", "RoleDefinition"]) {
      expect(ADMINISTRATION_RESOURCES.has(resource)).toBe(true);
    }
    // screens every user keeps: their own work, not administration
    for (const resource of ["WebMapService", "Keyword", "BackgroundProcess", "DatasetMetadataRecord"]) {
      expect(ADMINISTRATION_RESOURCES.has(resource)).toBe(false);
    }
  });
});

describe("resource checks for a logged-in user", () => {
  const asUser = (action: string, resource: string, snapshot = PLAIN) =>
    canAccessFromSnapshot({ action, resource, authenticated: true, snapshot });

  it("keeps ordinary resources open to every user, as before #836", () => {
    for (const action of ["list", "show", "create", "edit", "delete"]) {
      expect(asUser(action, "WebMapService")).toBe(true);
    }
  });

  it("denies the administration screens to a user without administration", () => {
    for (const action of ["list", "show", "create", "edit", "delete"]) {
      expect(asUser(action, "User")).toBe(false);
      expect(asUser(action, "PeriodicTask")).toBe(false);
    }
    // no role name grants administration until #736 fills the table
    expect(ADMINISTRATION_ROLES.size).toBe(0);
    expect(
      canAccessFromSnapshot({
        action: "list",
        resource: "User",
        authenticated: true,
        snapshot: { roles: ["organization_admin"], isSuperuser: false },
      })
    ).toBe(false);
  });

  it("grants them to a superuser and to a #736 administration role", () => {
    expect(asUser("list", "User", SUPERUSER)).toBe(true);
    expect(
      canAccessFromSnapshot({
        action: "list",
        resource: "User",
        authenticated: true,
        snapshot: { roles: ["organization_admin"], isSuperuser: false },
        administrationRoles: ORGANIZATION_ADMIN,
      })
    ).toBe(true);
  });
});

describe("anonymous checks", () => {
  it("denies everything outside #833's public set, which is still empty", () => {
    expect(PUBLIC_READ_RESOURCES.size).toBe(0);
    for (const action of ["list", "show", "create", "edit", "delete"]) {
      expect(asAnonymous(action, "WebMapService")).toBe(false);
      expect(asAnonymous(action, "User")).toBe(false);
    }
  });
});

describe("records carrying #738's allowedActions", () => {
  const asRecord = (
    action: string,
    resource: string,
    allowedActions?: string[]
  ) =>
    canAccessFromSnapshot({
      action,
      resource,
      record: { id: "1", ...(allowedActions ? { allowedActions } : {}) },
      authenticated: true,
      snapshot: PLAIN,
    });

  it("judges the action by the field: the name must be in it", () => {
    expect(asRecord("show", "WebMapService", ["view"])).toBe(true);
    expect(asRecord("edit", "WebMapService", ["view"])).toBe(false);
    expect(asRecord("edit", "WebMapService", ["view", "change"])).toBe(true);
    expect(asRecord("delete", "WebMapService", ["view", "change"])).toBe(false);
  });

  it("lets the field answer for administration records too - it already reflects the scoped role", () => {
    expect(asRecord("edit", "User", ["change"])).toBe(true);
  });

  it("falls back to the resource table when the field is absent, never guessing", () => {
    expect(asRecord("edit", "WebMapService")).toBe(true);
    expect(asRecord("edit", "User")).toBe(false);
    // an action with no record-level spelling stays a resource-level decision
    expect(
      canAccessFromSnapshot({
        action: "create",
        resource: "WebMapService",
        record: { id: "1", allowedActions: [] },
        authenticated: true,
        snapshot: PLAIN,
      })
    ).toBe(true);
  });
});
