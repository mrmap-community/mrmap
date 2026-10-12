import { render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RelatedResourceField from "./RelatedResourceField";

const state = vi.hoisted(() => ({
  related: undefined as { type?: string; id?: string } | undefined,
  relatedRecord: undefined as { stringRepresentation?: string } | undefined,
  asked: undefined as
    { resource: string; id: string; enabled: boolean } | undefined,
}));

vi.mock("react-admin", () => ({
  useFieldValue: () => state.related,
  useCreatePath:
    () =>
    ({ resource, type, id }: { resource: string; type: string; id: string }) =>
      `/${resource}/${id}/${type}`,
  useGetOne: (
    resource: string,
    params: { id: string },
    options: { enabled: boolean },
  ) => {
    state.asked = { resource, id: params.id, enabled: options.enabled };
    return { data: state.relatedRecord };
  },
  Link: ({
    to,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { to: string }) => (
    <a href={to} {...props} />
  ),
}));

beforeEach(() => {
  state.related = undefined;
  state.relatedRecord = undefined;
  state.asked = undefined;
});

describe("RelatedResourceField", () => {
  it("links to the resource of the process and names it", () => {
    state.related = { type: "WmsProxyService", id: "8c8d" };
    state.relatedRecord = { stringRepresentation: "weather service" };
    render(<RelatedResourceField source="relatedResource" />);
    const link = screen.getByRole("link", { name: "weather service" });
    expect(link).toHaveAttribute("href", "/WmsProxyService/8c8d/show");
    expect(state.asked).toEqual({
      resource: "WmsProxyService",
      id: "8c8d",
      enabled: true,
    });
  });

  it("falls back to type and id while the name is not answered", () => {
    state.related = { type: "WfsProxyService", id: "1a2b" };
    render(<RelatedResourceField source="relatedResource" />);
    expect(
      screen.getByRole("link", { name: "WfsProxyService #1a2b" }),
    ).toHaveAttribute("href", "/WfsProxyService/1a2b/show");
  });

  it("shows nothing for a process which does not name a resource", () => {
    render(<RelatedResourceField source="relatedResource" />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(state.asked?.enabled).toEqual(false);
  });
});
