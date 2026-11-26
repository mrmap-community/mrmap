import type { ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ResourceListCard from "./ResourceListCard";

const mocks = vi.hoisted(() => ({ list: vi.fn(), card: vi.fn() }));

vi.mock("react-admin", () => ({
  useResourceDefinition: ({ resource }: { resource: string }) => ({ name: resource, hasCreate: true }),
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
});
