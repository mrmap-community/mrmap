import { type ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import useServiceAlerts from "../../Resource/ServiceAlert/useServiceAlerts";
import ServiceAttentionCard from "./ServiceAttentionCard";

/** the react-admin Link accepts a path string or a `{pathname, search}` pair,
 *  which the router joins the way the `Count` component links its queues */
type LinkTarget = string | { pathname: string; search?: string };

const hrefOf = (to: LinkTarget): string => {
  if (typeof to === "string") {
    return to;
  }
  const search = to.search ?? "";
  if (!search) {
    return to.pathname;
  }
  return `${to.pathname}?${search.startsWith("?") ? search.slice(1) : search}`;
};

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key,
  useCreatePath: () =>
    ({ resource }: { resource: string }) => `/${resource}/list`,
  Link: ({ to, children }: { to: LinkTarget; children?: ReactNode }) => (
    <a href={hrefOf(to)}>{children}</a>
  ),
}));

vi.mock("../../Resource/ServiceAlert/useServiceAlerts", () => ({
  default: vi.fn(),
}));

const answered = (alerts: Record<string, unknown>[], total: number) => {
  vi.mocked(useServiceAlerts).mockReturnValue({
    data: alerts,
    total,
    error: undefined,
    isPending: false,
  } as unknown as ReturnType<typeof useServiceAlerts>);
};

beforeEach(() => {
  vi.mocked(useServiceAlerts).mockReset();
});

describe("ServiceAttentionCard", () => {
  it("answers nothing while there is no attention", () => {
    answered([], 0);
    const { container } = render(<ServiceAttentionCard />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names every alert of the top rows and links it to its record", () => {
    answered(
      [
        {
          id: "a1",
          severity: "warning",
          category: "harvest_overdue",
          serviceTitle: "Catalogue of things",
          targetPath: "/CatalogueService/c1/show",
        },
      ],
      1,
    );
    render(<ServiceAttentionCard />);
    expect(screen.getByText("serviceAlerts.title")).toBeInTheDocument();
    const row = screen.getByRole("link", {
      name: "Catalogue of things",
    });
    expect(row).toHaveAttribute("href", "/CatalogueService/c1/show");
    expect(
      screen.getByText(/serviceAlerts\.categories\.harvest_overdue/),
    ).toBeInTheDocument();
  });

  it("links the unfiltered list beside the lens of the catalogues", () => {
    answered(
      [
        {
          id: "a1",
          severity: "error",
          category: "monitoring_failed",
          serviceTitle: "Some map service",
          targetPath: "/WebMapService/w1/show",
        },
      ],
      42,
    );
    render(<ServiceAttentionCard />);
    expect(
      screen.getByRole("link", { name: "serviceAlerts.viewAll" }),
    ).toHaveAttribute("href", "/ServiceAlert/list");
    // the lens opens the alerts list with the filter the api answers for the
    // kind of service - the path from "catalogues came back broken" to the
    // alerts of the catalogues, whatever outnumbers the rows (#1086)
    expect(
      screen.getByRole("link", {
        name: "serviceAlerts.viewCatalogueAlerts",
      }),
    ).toHaveAttribute(
      "href",
      '/ServiceAlert/list?filter={"serviceType":"CatalogueService"}',
    );
  });
});
