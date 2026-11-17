/**
 * Pins the resource-level access policy of #836 - the whole table behind
 * `authProvider.canAccess`, judged without react-admin:
 *
 * - administration resources need a snapshot with administration, which is
 *   `who-am-i`'s `isSuperuser` or a slug from the #736 builtin catalogue
 *   table (specs also inject their sets to pin the wiring);
 * - everything else stays as it is today: every logged-in user may reach it,
 *   the backend keeps enforcing the records;
 * - anonymous requests are denied while #833 has not chosen its public set;
 * - a record that carries #738's `allowedActions` is judged by that field
 *   alone - the policy never guesses a record permission it did not get.
 *
 * The second suite pins the #736 slug resolution the snapshot is built from:
 * who-am-i answers role row ids, only the role API answers slugs, and the
 * organization an administrator administrates is read off the role's own
 * organization.
 */
import { describe, expect, it } from "vitest";

import {
  ADMINISTRATION_RESOURCES,
  ADMINISTRATION_ROLES,
  ANONYMOUS_SNAPSHOT,
  ORGANIZATION_ADMINISTRATION_ROLE,
  PUBLIC_READ_RESOURCES,
  callerRoleIdsFromWhoAmI,
  canAccessFromSnapshot,
  hasAdministration,
  isPlatformAdministration,
  permissionSnapshotFromWhoAmI,
  resolveAdministrationFromRoles,
  type PermissionSnapshot,
} from "./permissions";

const PLAIN: PermissionSnapshot = {
  roles: [], administeredOrganizationIds: [], isSuperuser: false,
};
const SUPERUSER: PermissionSnapshot = {
  roles: [], administeredOrganizationIds: [], isSuperuser: true,
};

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
    ).toEqual({
      roles: [], administeredOrganizationIds: [], isSuperuser: true,
    });
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

  it("reads the role row ids the shipped who-am-i carries instead of names", () => {
    // the `roles` relationship of #736 is a resource identifier list: it
    // names the caller's Role rows by id, and ids are not slugs - they are
    // the input of `resolveAdministrationFromRoles`, never the table's key
    expect(callerRoleIdsFromWhoAmI({
      data: { relationships: { roles: { data: [
        { type: "Role", id: "11" }, "12", { type: "Role" }, null,
      ] } } },
    })).toEqual(["11", "12"]);
    expect(callerRoleIdsFromWhoAmI({ data: { attributes: {} } })).toEqual([]);
    // and those ids grant nothing on their own
    expect(permissionSnapshotFromWhoAmI({
      data: { relationships: { roles: { data: [{ type: "Role", id: "11" }] } } },
    }).roles).toEqual([]);
  });
});

describe("role slug resolution of #736", () => {
  const rolesBody = {
    data: [
      {
        id: "11",
        attributes: { isActive: true },
        relationships: {
          role_definition: { data: { type: "RoleDefinition", id: "3" } },
          organization: { data: { type: "Organization", id: "7" } },
        },
      },
      {
        // the same caller may hold a retired role: it grants nothing, and
        // it must not make its organization administrated either
        id: "12",
        attributes: { isActive: false },
        relationships: {
          role_definition: { data: { type: "RoleDefinition", id: "3" } },
          organization: { data: { type: "Organization", id: "8" } },
        },
      },
      {
        // a PLATFORM scoped role row has no organization
        id: "13",
        attributes: { isActive: true },
        relationships: {
          role_definition: { data: { type: "RoleDefinition", id: "5" } },
          organization: { data: null },
        },
      },
      {
        // a role whose definition the second read did not answer
        id: "14",
        attributes: { isActive: true },
        relationships: { role_definition: { data: { type: "RoleDefinition", id: "99" } } },
      },
    ],
  };
  const definitionsBody = {
    data: [
      { id: "3", attributes: { slug: "organization_admin" } },
      { id: "5", attributes: { slug: "platform_admin" } },
    ],
  };

  it("answers the active slugs and the organizations of the administration role", () => {
    expect(resolveAdministrationFromRoles(rolesBody, definitionsBody)).toEqual({
      roles: ["organization_admin", "platform_admin"],
      administeredOrganizationIds: ["7"],
    });
  });

  it("answers nothing without the definition documents the ids came from", () => {
    expect(resolveAdministrationFromRoles(rolesBody, undefined)).toEqual({
      roles: [], administeredOrganizationIds: [],
    });
    expect(resolveAdministrationFromRoles(undefined, undefined)).toEqual({
      roles: [], administeredOrganizationIds: [],
    });
  });

  it("names the organization administration slug the resolver reads off", () => {
    // the constant is the same slug the seeded catalogue and the table name
    expect(ORGANIZATION_ADMINISTRATION_ROLE).toBe("organization_admin");
    expect(ADMINISTRATION_ROLES.has(ORGANIZATION_ADMINISTRATION_ROLE)).toBe(true);
  });
});

describe("administration", () => {
  it("is answered by the superuser flag", () => {
    expect(hasAdministration(SUPERUSER)).toBe(true);
    expect(hasAdministration(PLAIN)).toBe(false);
  });

  it("is answered by the #736 catalogue names, and by them alone", () => {
    expect(
      hasAdministration({ ...PLAIN, roles: ["organization_admin"] })
    ).toBe(true);
    expect(
      hasAdministration({ ...PLAIN, roles: ["platform_admin"] })
    ).toBe(true);
    // the rest of the seeded catalogue reads administration but is not it
    for (const slug of ["harvester", "support", "service_account", "resource_editor"]) {
      expect(
        hasAdministration({ ...PLAIN, roles: [slug] }),
        `the role ${slug} must not answer administration`
      ).toBe(false);
    }
  });

  it("is answered by any name the injected table carries", () => {
    expect(
      hasAdministration(
        { roles: ["organization_admin"], administeredOrganizationIds: [], isSuperuser: false },
        ORGANIZATION_ADMIN
      )
    ).toBe(true);
    expect(
      hasAdministration({ ...PLAIN, roles: ["editor"] }, ORGANIZATION_ADMIN)
    ).toBe(false);
  });

  it("of the whole instance is the superuser flag or the platform holder", () => {
    expect(isPlatformAdministration(SUPERUSER)).toBe(true);
    expect(
      isPlatformAdministration({ ...PLAIN, roles: ["platform_admin"] })
    ).toBe(true);
    // the organization holder administers its organization, not the instance
    expect(
      isPlatformAdministration({
        ...PLAIN, roles: ["organization_admin"], administeredOrganizationIds: ["7"],
      })
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
    // a role outside the #736 catalogue table keeps the screens shut too
    expect(
      canAccessFromSnapshot({
        action: "list",
        resource: "User",
        authenticated: true,
        snapshot: { ...PLAIN, roles: ["harvester"] },
      })
    ).toBe(false);
  });

  it("grants them to a superuser and to every #736 administration role", () => {
    expect(asUser("list", "User", SUPERUSER)).toBe(true);
    // the organization administrator reaches the administration resources
    // through the very same table; which records it may read stays the
    // backend's answer (#836's accepted precedence), the screens scope
    // themselves by the administered organizations
    expect(
      asUser("list", "User", {
        roles: ["organization_admin"], administeredOrganizationIds: ["7"], isSuperuser: false,
      })
    ).toBe(true);
    expect(
      asUser("list", "RoleDefinition", {
        roles: ["platform_admin"], administeredOrganizationIds: [], isSuperuser: false,
      })
    ).toBe(true);
    // and the injected table still overrules nothing, it only replaces
    expect(
      canAccessFromSnapshot({
        action: "list",
        resource: "User",
        authenticated: true,
        snapshot: { ...PLAIN, roles: ["organization_admin"] },
        administrationRoles: new Set<string>(),
      })
    ).toBe(false);
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
