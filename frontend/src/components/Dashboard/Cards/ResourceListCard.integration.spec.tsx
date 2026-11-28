import {
  CoreAdminContext,
  ResourceDefinitionContextProvider,
  testDataProvider,
  useCanAccess,
} from "react-admin";
import type { AuthProvider, DataProvider } from "react-admin";
import { MemoryRouter, useLocation } from "react-router-dom";

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  ANONYMOUS_SNAPSHOT,
  canAccessFromSnapshot,
  type PermissionSnapshot,
} from "../../../providers/permissions";
import ResourceListCard from "./ResourceListCard";

/**
 * The cards of #1804, judged by where the caller ends up. The real react-admin
 * guard the shipped bundle runs (`useRequireAccess` behind the list controller)
 * answers together with the real permission table of #836, so nothing here
 * stubs the check whose `false` answer navigated the application away: a test
 * reads the location of the caller, never the props a card was given.
 */

vi.mock("../../../context/HttpClientContext", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../context/HttpClientContext")>()),
  useHttpClientContext: () => ({
    api: { getOperation: () => undefined },
    isPending: false,
    error: undefined,
    realtimeIsReady: 0,
  }),
}));

/** the persona of the report: a member holding a builtin role which is not one
 *  of the administration roles of #736 */
const member: PermissionSnapshot = { ...ANONYMOUS_SNAPSHOT, roles: ["viewer"] };

const authProvider: AuthProvider = {
  login: async () => true,
  logout: async () => undefined,
  checkAuth: async () => undefined,
  checkError: async () => undefined,
  canAccess: async ({ action, resource, record }) =>
    canAccessFromSnapshot({
      action,
      resource,
      record: record as Record<string, unknown> | undefined,
      authenticated: true,
      snapshot: member,
    }),
};

const definitions = Object.fromEntries(
  ["User", "WebMapService"].map((resource) => [resource, { name: resource }]),
);

/** where the caller stands - the observation the report made in a browser */
const Location = () => {
  const location = useLocation();
  return <span>at {location.pathname}</span>;
};

/**
 * The settle signal, read from the same `canAccess` query the guard of the
 * controller subscribes to: once it answers, the navigation of that guard has
 * run too, so a test never races the navigation it wants to rule out.
 */
const AccessAnswer = ({ resource }: { resource: string }) => {
  const { canAccess, isPending } = useCanAccess({ action: "list", resource });
  return <span>check {isPending ? "pending" : String(canAccess)}</span>;
};

const renderCard = async (resource: string, withList: boolean) => {
  const getList = vi.fn(async (_resource: string) => ({ data: [], total: 7 }));
  const dataProvider = {
    ...testDataProvider({ getList }),
    subscribe: async () => undefined,
    unsubscribe: async () => undefined,
  } as unknown as DataProvider;
  render(
    <MemoryRouter initialEntries={["/"]}>
      <CoreAdminContext authProvider={authProvider} dataProvider={dataProvider}>
        <ResourceDefinitionContextProvider definitions={definitions}>
          <ResourceListCard resource={resource} withList={withList} compact={!withList} />
          <AccessAnswer resource={resource} />
          <Location />
        </ResourceDefinitionContextProvider>
      </CoreAdminContext>
    </MemoryRouter>,
  );
  const answer = await screen.findByText(/^check (true|false)$/);
  // a denied guard navigates from its own effect, so the location of the caller
  // is only an answer once those effects have run - reading it earlier would
  // let a bounce which is still queued read as the caller having stayed
  await new Promise((settle) => setTimeout(settle, 100));
  return {
    getList,
    settled: answer.textContent,
    where: screen.getByText(/^at /).textContent,
  };
};

describe("the count card of a resource the caller may not list", () => {
  it("is judged against the table of #836", async () => {
    const { settled } = await renderCard("User", false);
    expect(settled).toBe("check false");
  });

  // the bug: the guard of the list controller turned the denied check of the
  // card into a navigation of the whole application, so a member who logged in
  // never saw the dashboard, only the access denied state
  it("keeps the caller on the dashboard", async () => {
    const { where } = await renderCard("User", false);
    expect(where).toBe("at /");
  });

  // the card is absent rather than a number, and the collection of the denied
  // resource is not read at all
  it("reads nothing of the denied resource", async () => {
    const { getList } = await renderCard("User", false);
    expect(getList.mock.calls.map(([resource]) => resource)).not.toContain("User");
    expect(document.querySelector('a[href="/User"]')).toBeNull();
  });
});

describe("the count card of a resource the caller may list", () => {
  it("answers its count and stays on the dashboard", async () => {
    const { getList, settled, where } = await renderCard("WebMapService", false);
    expect(settled).toBe("check true");
    expect(where).toBe("at /");
    expect(await screen.findByText("7")).toBeInTheDocument();
    expect(getList.mock.calls.map(([resource]) => resource)).toContain("WebMapService");
  });
});

describe("the list card of a resource the caller may not list", () => {
  // a card which lists records *is* the screen of its resource, so the opt-out
  // of #1804 belongs to the count only: a denied screen keeps navigating
  it("keeps the navigation react-admin performs for a denied route", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <CoreAdminContext authProvider={authProvider} dataProvider={testDataProvider({})}>
          <ResourceDefinitionContextProvider definitions={definitions}>
            <ResourceListCard resource="User" />
            <Location />
          </ResourceDefinitionContextProvider>
        </CoreAdminContext>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/^at /).textContent).toBe("at /access-denied"));
  });
});
