import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ContextualIncidents from "./ContextualIncidents";
import useContextualIncidents from "./useContextualIncidents";

import "@testing-library/jest-dom/vitest";

const state = vi.hoisted(() => ({
  record: { id: 42 } as Record<string, unknown> | undefined,
  resource: "HarvestingJob" as string | undefined,
}));

vi.mock("react-admin", () => ({
  useRecordContext: () => state.record,
  useResourceContext: () => state.resource,
}));

vi.mock("./useContextualIncidents", () => ({ default: vi.fn() }));

vi.mock("./IncidentContextBanner", () => ({
  default: ({ incidents }: { incidents: unknown[] }) => (
    <div data-testid="banner">{incidents.length}</div>
  ),
}));
vi.mock("./IncidentContextHistory", () => ({
  default: ({ incidents }: { incidents: unknown[] }) => (
    <div data-testid="history">{incidents.length}</div>
  ),
}));

const hook = (result: Partial<ReturnType<typeof useContextualIncidents>>) =>
  vi.mocked(useContextualIncidents).mockReturnValue({
    active: [],
    resolved: [],
    isPending: false,
    error: null,
    ...result,
  } as ReturnType<typeof useContextualIncidents>);

describe("ContextualIncidents", () => {
  it("says nothing while the read is pending", () => {
    hook({ isPending: true, active: [{ id: 1 } as never] });
    render(<ContextualIncidents />);
    expect(screen.queryByTestId("banner")).not.toBeInTheDocument();
  });

  it("says nothing while the api cannot be read", () => {
    hook({ error: new Error("gone"), active: [{ id: 1 } as never] });
    render(<ContextualIncidents />);
    expect(screen.queryByTestId("banner")).not.toBeInTheDocument();
  });

  it("raises no alarm when nothing is active or resolved", () => {
    hook({});
    render(<ContextualIncidents />);
    expect(screen.queryByTestId("banner")).not.toBeInTheDocument();
    expect(screen.queryByTestId("history")).not.toBeInTheDocument();
  });

  it("shows the banner and the history of this record", () => {
    hook({
      active: [{ id: 1 } as never, { id: 2 } as never],
      resolved: [{ id: 3 } as never],
    });
    render(<ContextualIncidents />);
    expect(screen.getByTestId("banner")).toHaveTextContent("2");
    expect(screen.getByTestId("history")).toHaveTextContent("1");
  });

  it("omits the history when the caller does not ask for it", () => {
    hook({ active: [{ id: 1 } as never], resolved: [{ id: 3 } as never] });
    render(<ContextualIncidents showHistory={false} />);
    expect(screen.getByTestId("banner")).toBeInTheDocument();
    expect(screen.queryByTestId("history")).not.toBeInTheDocument();
  });
});
