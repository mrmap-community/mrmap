import type { ReactNode } from "react";
import { useRecordContext } from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ScheduleRowActions from "./ScheduleRowActions";

vi.mock("react-admin", () => ({
  Button: ({ label, to }: { label?: string; to?: string }) =>
    to !== undefined ? <a href={to}>{label}</a> : <span>{label}</span>,
  Link: ({ to, children }: { to: string; children?: ReactNode }) => (
    <a href={to}>{children}</a>
  ),
  useRecordContext: vi.fn(),
}));

// the button answers its own states in its spec; here it only marks that the
// row of a schedule which may be harvested carries it
vi.mock("../Generic/ServiceShow/RunHarvestingButton", () => ({
  default: ({ serviceId }: { serviceId?: string }) => (
    <span>run:{serviceId}</span>
  ),
}));

describe("ScheduleRowActions", () => {
  it("answers nothing for a row without a catalogue", () => {
    vi.mocked(useRecordContext).mockReturnValue({ id: "1" });
    const { container } = render(<ScheduleRowActions />);
    expect(container).toBeEmptyDOMElement();
  });

  it("links to the runs of the catalogue the relation answers", () => {
    vi.mocked(useRecordContext).mockReturnValue({
      id: "1",
      service: { id: "17" },
    });
    render(<ScheduleRowActions />);
    expect(screen.getByText("run:17")).toBeInTheDocument();
    expect(
      screen.getByText("harvestingSchedules.runs").closest("a"),
    ).toHaveAttribute(
      "href",
      "/CatalogueService/17/show/HarvestingJob",
    );
  });

  it("accepts the relation as a bare identifier", () => {
    vi.mocked(useRecordContext).mockReturnValue({ id: "1", service: "4" });
    render(<ScheduleRowActions />);
    expect(screen.getByText("run:4")).toBeInTheDocument();
  });
});
