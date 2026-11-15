import { type ReactNode } from "react";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type OperationalIncidentRecord } from "../incidentContract";
import IncidentContextBanner from "./IncidentContextBanner";

import "@testing-library/jest-dom/vitest";

vi.mock("react-admin", () => ({
  useTranslate: () => (key: string, options?: Record<string, unknown>) => {
    if (options && typeof options._ === "string") return options._;
    if (options && options.smart_count != null)
      return `${key}#${options.smart_count}`;
    if (options && options.attempt != null)
      return `${key}#${options.attempt}/${options.total}`;
    return key;
  },
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

const incident = (
  overrides: Partial<OperationalIncidentRecord> & { id: string | number },
): OperationalIncidentRecord => ({
  code: "csw.timeout",
  sourceType: "csw",
  severity: "error",
  state: "retrying",
  summary: `summary-${overrides.id}`,
  occurrenceCount: 1,
  firstOccurrence: "2026-11-14T10:00:00Z",
  lastOccurrence: "2026-11-14T10:00:00Z",
  targetPath: `/WebMapService/${overrides.id}/show`,
  ...overrides,
});

describe("IncidentContextBanner", () => {
  it("shows nothing when no incident is active", () => {
    const { container } = render(<IncidentContextBanner incidents={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the safe summary of every active incident, never a per-retry copy", () => {
    render(
      <IncidentContextBanner
        incidents={[
          incident({ id: 1, summary: "CSW endpoint timed out" }),
          incident({ id: 2, summary: "harvesting chord stalled" }),
        ]}
      />,
    );
    expect(screen.getByText("CSW endpoint timed out")).toBeInTheDocument();
    expect(screen.getByText("harvesting chord stalled")).toBeInTheDocument();
  });

  it("is an alert for an error and a status for a warning", () => {
    render(<IncidentContextBanner incidents={[incident({ id: 1 })]} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    render(
      <IncidentContextBanner
        incidents={[incident({ id: 2, severity: "warning" })]}
      />,
    );
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("names the retry progress only when the retry state is known", () => {
    render(
      <IncidentContextBanner
        incidents={[
          incident({ id: 1, retryAttempt: 4, retryTotal: 10, nextRetryAt: "2026-11-14T11:00:00Z" }),
        ]}
      />,
    );
    expect(screen.getByText("contextualIncidents.retry#4/10")).toBeInTheDocument();
    expect(screen.getByTestId("relative-nextRetryAt")).toBeInTheDocument();
  });

  it("folds the occurrences into one banner and counts them", () => {
    render(
      <IncidentContextBanner
        incidents={[incident({ id: 1, occurrenceCount: 7 })]}
      />,
    );
    expect(screen.getByText("contextualIncidents.occurrences#7")).toBeInTheDocument();
  });

  it("links only to the target path the api answered", () => {
    const { rerender } = render(
      <IncidentContextBanner incidents={[incident({ id: 5 })]} />,
    );
    const link = screen.getByRole("link", {
      name: "contextualIncidents.viewDetails",
    });
    expect(link).toHaveAttribute("href", "/WebMapService/5/show");
    rerender(
      <IncidentContextBanner
        incidents={[incident({ id: 6, targetPath: null })]}
      />,
    );
    expect(
      screen.queryByRole("link", { name: "contextualIncidents.viewDetails" }),
    ).not.toBeInTheDocument();
  });

  it("summarises the active incidents it does not spell out", () => {
    render(
      <IncidentContextBanner
        incidents={[
          incident({ id: 1 }),
          incident({ id: 2 }),
          incident({ id: 3 }),
          incident({ id: 4 }),
        ]}
      />,
    );
    expect(screen.getAllByRole("alert")).toHaveLength(3);
    expect(screen.getByText("contextualIncidents.moreActive#1")).toBeInTheDocument();
  });
});
