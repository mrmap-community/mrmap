import { type ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type OperationalIncidentRecord } from "../incidentContract";
import IncidentContextHistory from "./IncidentContextHistory";

import "@testing-library/jest-dom/vitest";

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string, options?: Record<string, unknown>) =>
    options && typeof options._ === "string" ? options._ : key,
  Link: ({ to, children }: { to: string; children: ReactNode }) => (
    <a href={to}>{children}</a>
  ),
  BasenameContextProvider: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("../../../Field/RelativeDateField", () => ({
  default: ({ source }: { source: string }) => (
    <span data-testid={`relative-${source}`} />
  ),
}));

const resolved = (
  overrides: Partial<OperationalIncidentRecord> & { id: string | number },
): OperationalIncidentRecord => ({
  code: "update.timeout",
  sourceType: "update",
  severity: "warning",
  state: "resolved",
  summary: `summary-${overrides.id}`,
  occurrenceCount: 1,
  firstOccurrence: "2026-11-10T10:00:00Z",
  lastOccurrence: "2026-11-10T10:00:00Z",
  resolvedAt: "2026-11-10T10:00:00Z",
  targetPath: `/WebMapService/${overrides.id}/show`,
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
          resolved({ id: 1, resolvedAt: "2026-11-10T10:00:00Z" }),
          resolved({ id: 2, resolvedAt: "2026-11-12T10:00:00Z" }),
          resolved({ id: 3, resolvedAt: "2026-11-11T10:00:00Z" }),
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
    render(<IncidentContextHistory incidents={[resolved({ id: 1 })]} />);
    expect(screen.getByTestId("relative-resolvedAt")).toBeInTheDocument();
  });

  it("links a resolved incident only to its answered target path", () => {
    render(
      <IncidentContextHistory
        incidents={[resolved({ id: 8, targetPath: null })]}
      />,
    );
    expect(
      screen.queryByRole("link", { name: "contextualIncidents.viewDetails" }),
    ).not.toBeInTheDocument();
  });
});
