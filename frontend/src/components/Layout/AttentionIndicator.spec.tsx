import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ServiceAttentionCard from "../Dashboard/Cards/ServiceAttentionCard";
import useServiceAlerts from "../Resource/ServiceAlert/useServiceAlerts";
import AttentionIndicator from "./AttentionIndicator";

const redirect = vi.hoisted(() => vi.fn());
vi.mock("../Resource/ServiceAlert/useServiceAlerts", () => ({
  default: vi.fn(),
}));
vi.mock("react-admin", () => ({
  useCreatePath: () => () => "/ServiceAlert",
  useRedirect: () => redirect,
  useTranslate: () => (key: string) => key,
  Link: ({ to, children }: { to: string; children: React.ReactNode }) => (
    <a href={to}>{children}</a>
  ),
}));
const mockAlerts = vi.mocked(useServiceAlerts);
beforeEach(() => vi.clearAllMocks());
const state = (overrides = {}) =>
  ({
    data: [
      {
        id: "one",
        severity: "error",
        serviceTitle: "Broken WMS",
        targetPath: "/WebMapService/one/show",
        category: "monitoring_failed",
      },
    ],
    total: 12,
    error: null,
    isPending: false,
    ...overrides,
  }) as ReturnType<typeof useServiceAlerts>;

describe("cross-service attention surfaces", () => {
  it("shows the count, highest severity and full list destination", () => {
    mockAlerts.mockReturnValue(state());
    render(<AttentionIndicator />);
    const chip = screen.getByRole("button", { name: "serviceAlerts.count" });
    expect(chip).toHaveTextContent("12");
    expect(chip).toHaveClass("MuiChip-colorError");
    fireEvent.click(chip);
    expect(redirect).toHaveBeenCalledWith("/ServiceAlert");
  });
  it.each([
    { total: 0 },
    { error: { status: 403 } },
    { error: { status: 401 } },
    { isPending: true },
  ])("hides both surfaces for %j", (overrides) => {
    mockAlerts.mockReturnValue(state(overrides));
    const { container } = render(
      <>
        <AttentionIndicator />
        <ServiceAttentionCard />
      </>,
    );
    expect(container).toBeEmptyDOMElement();
  });
  it("links dashboard problems to their workflow and offers the full list", () => {
    mockAlerts.mockReturnValue(state());
    render(<ServiceAttentionCard />);
    expect(screen.getByRole("link", { name: "Broken WMS" })).toHaveAttribute(
      "href",
      "/WebMapService/one/show",
    );
    expect(
      screen.getByRole("link", { name: "serviceAlerts.viewAll" }),
    ).toHaveAttribute("href", "/ServiceAlert");
    expect(
      screen.getByText(/serviceAlerts.categories.monitoring_failed/),
    ).toBeInTheDocument();
  });
});
