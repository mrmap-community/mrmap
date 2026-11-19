/**
 * Pins the audit-trail link the administration screens of #741 name in their
 * toolbar: it must point at the `history` child route of the resource it is
 * given, because that is the route `MrMapFrontend` registers for every resource
 * whose schema answers `list_Historical<Resource>`. A link spelled differently
 * than that route answers the frontend's empty page instead of the changelog,
 * and the audit trail of the role system is exactly what the issue promises an
 * administrator can reach.
 */
import { type ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import HistoryChangelogLink from "./HistoryChangelogLink";

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string): string => key,
  // the screen composes a button over react-admin's Link; the mock keeps both
  // halves, so the assertion reads the target the router would follow
  Button: ({
    component: Component,
    to,
    children,
  }: {
    component: (props: { to: string; children?: ReactNode }) => ReactNode;
    to: string;
    children?: ReactNode;
  }) => <Component to={to}>{children}</Component>,
  Link: ({ to, children }: { to: string; children?: ReactNode }) => (
    <a href={to}>{children}</a>
  ),
}));

describe("HistoryChangelogLink", () => {
  it("links the history route of the resource it names", () => {
    render(
      <HistoryChangelogLink
        resource="RoleDefinition"
        label="administration.audit.roles"
      />,
    );

    expect(
      screen.getByRole("link", { name: "administration.audit.roles" }),
    ).toHaveAttribute("href", "/RoleDefinition/history");
  });

  it("asks its own label, so a screen names its own wording", () => {
    render(
      <HistoryChangelogLink
        resource="RoleMembership"
        label="administration.audit.memberships"
      />,
    );

    expect(
      screen.getByRole("link", { name: "administration.audit.memberships" }),
    ).toHaveAttribute("href", "/RoleMembership/history");
  });
});
