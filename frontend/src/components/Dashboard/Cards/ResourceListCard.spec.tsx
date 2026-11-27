import type { ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ResourceListCard from "./ResourceListCard";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  card: vi.fn(),
  access: { canAccess: true as boolean | undefined, isPending: false },
}));

vi.mock("react-admin", () => ({
  useResourceDefinition: ({ resource }: { resource: string }) => ({ name: resource, hasCreate: true }),
  useCanAccess: () => mocks.access,
  ListBase: (props: { children: ReactNode }) => { mocks.list(props); return props.children; },
  WithListContext: ({ render }: { render: (context: { total: number }) => ReactNode }) => render({ total: 12 }),
  CreateButton: () => <button>Create</button>,
}));
vi.mock("./CardWithIcon", () => ({
  default: (props: { children: ReactNode; subtitle: ReactNode }) => {
    mocks.card(props);
    return <div>{props.subtitle}{props.children}</div>;
  },
}));
vi.mock("./ChangeLogList", () => ({ default: () => <div>History</div> }));

describe("ResourceListCard", () => {
  it("keeps create actions, history and children in the standard card", () => {
    render(<ResourceListCard resource="CatalogueService"><span>Content</span></ResourceListCard>);
    expect(screen.getByRole("button", { name: "Create" })).toBeInTheDocument();
    expect(screen.getByText("History")).toBeInTheDocument();
    expect(screen.getByText("Content")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({ perPage: 100, filter: undefined }));
    expect(mocks.card).toHaveBeenLastCalledWith(expect.objectContaining({ compact: false, to: "/CatalogueService" }));
  });

  it("omits create actions and history from compact count cards", () => {
    render(<ResourceListCard resource="WebMapService" compact withList={false} />);
    expect(screen.queryByRole("button", { name: "Create" })).not.toBeInTheDocument();
    expect(screen.queryByText("History")).not.toBeInTheDocument();
    expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({
      perPage: 1,
      filter: { is_update_candidate: false },
      queryOptions: { meta: { jsonApiParams: { "fields[WebMapService]": "id" } } },
    }));
    expect(mocks.card).toHaveBeenLastCalledWith(expect.objectContaining({ compact: true }));
  });

  // the count of a card is no screen, so its controller must not be the access
  // gated one: a denied answer there navigated the whole application to the
  // access denied state instead of leaving the caller on the dashboard (#1804)
  it("leaves the list controller of a count card ungated", () => {
    render(<ResourceListCard resource="User" compact withList={false} />);
    expect(mocks.list).toHaveBeenLastCalledWith(expect.objectContaining({
      disableAuthentication: true,
    }));
  });

  it("keeps the list card of a resource gated as its list screen is", () => {
    render(<ResourceListCard resource="User" />);
    expect(mocks.list).not.toHaveBeenLastCalledWith(expect.objectContaining({
      disableAuthentication: true,
    }));
  });

  // a denied resource is not read at all: the card is absent rather than a
  // number, which is how the other administrator cards of the dashboard answer
  // a caller who may not read them
  it("mounts neither controller nor card for a resource the caller may not list", () => {
    mocks.access.canAccess = false;
    try {
      render(<ResourceListCard resource="User" compact withList={false} />);
      expect(mocks.list).not.toHaveBeenCalled();
      expect(mocks.card).not.toHaveBeenCalled();
    } finally {
      mocks.access.canAccess = true;
    }
  });

  // while the check is still running the card stays away too, so a count is
  // never offered before the answer of `canAccess` exists
  it("waits for the access check before mounting a count card", () => {
    mocks.access.isPending = true;
    try {
      render(<ResourceListCard resource="User" compact withList={false} />);
      expect(mocks.list).not.toHaveBeenCalled();
    } finally {
      mocks.access.isPending = false;
    }
  });

  it("keeps the list card visible while its own check runs, as its screen is gated by the controller", () => {
    mocks.access.canAccess = false;
    try {
      render(<ResourceListCard resource="User" />);
      expect(mocks.list).toHaveBeenCalled();
      expect(mocks.card).toHaveBeenCalled();
    } finally {
      mocks.access.canAccess = true;
    }
  });
});
