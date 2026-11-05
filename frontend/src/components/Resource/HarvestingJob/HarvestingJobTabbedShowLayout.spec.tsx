import type { ReactNode } from "react";
import type { RaRecord } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import HarvestingJobTabbedShowLayout from "./HarvestingJobTabbedShowLayout";

const state = vi.hoisted(() => ({
  record: { id: 1 } as RaRecord | undefined,
  isPending: false,
  error: null as Error | null,
}));
vi.mock("react-admin", () => {
  const Container = ({
    children,
    label,
  }: {
    children: ReactNode;
    label?: string;
  }) => (
    <div>
      {typeof label === "string" ? label : null}
      {children}
    </div>
  );
  return {
    useShowContext: () => state,
    useTranslate: () => (key: string) => key,
    Loading: () => <span>Loading run</span>,
    TabbedShowLayout: Object.assign(Container, { Tab: Container }),
    SimpleShowLayout: Container,
    Labeled: Container,
    BooleanField: () => null,
    DateField: () => null,
    NumberField: ({ source }: { source: string }) => <span>{source}</span>,
    TextField: () => null,
  };
});
vi.mock("../../../jsonapi/components/ListGuesser", () => ({
  default: () => <span>Related records</span>,
}));
vi.mock("../../../jsonapi/components/ReferenceField", () => ({
  default: () => null,
}));
vi.mock("./HarvestingRunSummary", () => ({
  default: () => <span>Run summary</span>,
}));
vi.mock("./HarvestingJobTimingCharts", () => ({
  default: () => <span>Timing chart</span>,
}));
beforeEach(() => {
  state.record = { id: 1 };
  state.isPending = false;
  state.error = null;
});
describe("harvesting run detail layout", () => {
  it("renders a successfully loaded run rather than the error banner", () => {
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByText("Run summary")).toBeInTheDocument();
    expect(screen.getByText("harvestRun.configuration")).toBeInTheDocument();
    expect(screen.getAllByText("Timing chart")).toHaveLength(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("counts every collected kind by collecting state and tabs the application records", () => {
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByText("harvestRun.resultCounts")).toBeInTheDocument();
    for (const kind of ["Dataset", "Service", "Application"]) {
      for (const stateName of ["new", "updated", "existing", "duplicated"]) {
        expect(
          screen.getByText(`${stateName}${kind}MetadataCount`),
        ).toBeInTheDocument();
      }
    }
    // the applications appear both as a result-count row and as a tab of the
    // records the run collected
    expect(screen.getAllByText("harvestRun.applications").length).toBeGreaterThan(1);
  });
  it("shows loading while the request is pending", () => {
    state.isPending = true;
    state.record = undefined;
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByText("Loading run")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("waits for a record when one is not yet available", () => {
    state.record = undefined;
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByText("Loading run")).toBeInTheDocument();
  });
  it("shows an error only when the request fails", () => {
    state.record = undefined;
    state.error = new Error("Unavailable");
    render(<HarvestingJobTabbedShowLayout />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "harvestingActivity.loadError",
    );
    expect(screen.queryByText("Run summary")).not.toBeInTheDocument();
  });
});
