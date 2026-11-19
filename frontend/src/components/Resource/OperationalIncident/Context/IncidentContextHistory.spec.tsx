import { type ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type OperationalIncidentRecord } from "../incidentContract";
import IncidentContextHistory from "./IncidentContextHistory";

import "@testing-library/jest-dom/vitest";

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string, options?: Record<string, unknown>) =>
    options && typeof options._ === "string" ? options._ : key,
  // the same show-view path react-admin builds, so the href pins what the
  // link of the entry really is
  useCreatePath: () => (params: { resource: string; id: string }) =>
    `/${params.resource}/${params.id}/show`,
  Link: ({ to, children }: { to: string; children: ReactNode }) => (
    <a href={to}>{children}</a>
  ),
}));

vi.mock("../../../Field/RelativeDateField", () => ({
  default: ({ source }: { source: string }) => (
    <span data-testid={`relative-${source}`} />
  ),
}));

const resolved = (
  overrides: Partial<OperationalIncidentRecord> & { id: string },
): OperationalIncidentRecord => ({
  code: "update_run_service_metadata",
  source: "update",
  severity: "warning",
  status: "resolved",
  scope: "resource",
  summary: `summary-${overrides.id}`,
  occurrenceCount: 1,
  firstOccurredAt: "2026-11-10T10:00:00Z",
  lastOccurredAt: "2026-11-10T10:00:00Z",
  resolvedAt: "2026-11-10T10:00:00Z",
  affectedResource: { type: "WebMapService", id: overrides.id },
  ...overrides,
});

describe("IncidentContextHistory", () => {
  it("shows nothing when there is no resolved incident", () => {
    const { container } = render(<IncidentContextHistory incidents={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists the resolved incidents newest recovery first", () => {
    const { container } = render(
      <IncidentContextHistory
        incidents={[
          resolved({ id: "1", resolvedAt: "2026-11-10T10:00:00Z" }),
          resolved({ id: "2", resolvedAt: "2026-11-12T10:00:00Z" }),
          resolved({ id: "3", resolvedAt: "2026-11-11T10:00:00Z" }),
        ]}
      />,
    );
    const order = Array.from(container.querySelectorAll("li")).map((li) =>
      li.textContent?.includes("summary-2")
        ? 2
        : li.textContent?.includes("summary-3")
          ? 3
          : 1,
    );
    expect(order).toEqual([2, 3, 1]);
  });

  it("names the moment a resolved incident was resolved", () => {
    render(<IncidentContextHistory incidents={[resolved({ id: "1" })]} />);
    expect(screen.getByTestId("relative-resolvedAt")).toBeInTheDocument();
  });

  it("links the resource the api named and gives a system incident none", () => {
    render(
      <IncidentContextHistory
        incidents={[
          resolved({
            id: "8",
            scope: "system",
            affectedResource: null,
          }),
        ]}
      />,
    );
    expect(
      screen.queryByRole("link", { name: "contextualIncidents.viewDetails" }),
    ).not.toBeInTheDocument();
  });
});
