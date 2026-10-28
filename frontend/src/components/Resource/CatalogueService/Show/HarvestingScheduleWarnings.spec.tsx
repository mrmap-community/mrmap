import { useRecordContext } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import useServiceAlerts from "../../ServiceAlert/useServiceAlerts";
import HarvestingScheduleWarnings from "./HarvestingScheduleWarnings";

vi.mock("react-admin", () => ({
  useRecordContext: vi.fn(),
}));
vi.mock("../../ServiceAlert/useServiceAlerts", () => ({
  default: vi.fn(() => ({ data: [] })),
}));

beforeEach(() => {
  vi.mocked(useRecordContext, { partial: true }).mockReturnValue({
    id: "csw-1",
  });
  vi.mocked(useServiceAlerts).mockReturnValue(
    { data: [] } as unknown as ReturnType<typeof useServiceAlerts>,
  );
});

describe("harvesting schedule warnings", () => {
  it("asks the alerts of the shown catalogue about its too tight schedules", () => {
    render(<HarvestingScheduleWarnings />);
    expect(useServiceAlerts).toHaveBeenCalledWith({
      service: "csw-1",
      category: "harvest_schedule_too_tight",
    });
  });

  it("names the schedule and the harvest which is tighter than it", () => {
    vi.mocked(useServiceAlerts).mockReturnValue({
      data: [
        {
          id: "harvest_schedule_too_tight:CatalogueService:7",
          message:
            'The schedule "*/5 * * * *" harvests this catalogue more often ' +
            "than a harvest of it takes: the harvests which finished measured " +
            "0:40:00 on average.",
        },
      ],
    } as unknown as ReturnType<typeof useServiceAlerts>);
    render(<HarvestingScheduleWarnings />);
    expect(screen.getByText(/0:40:00/)).toBeInTheDocument();
  });

  it("answers nothing while every schedule keeps up with its harvest", () => {
    const { container } = render(<HarvestingScheduleWarnings />);
    expect(container).toBeEmptyDOMElement();
  });

  it("asks about nothing outside of a catalogue", () => {
    vi.mocked(useRecordContext, { partial: true }).mockReturnValue(undefined);
    const { container } = render(<HarvestingScheduleWarnings />);
    expect(container).toBeEmptyDOMElement();
    expect(useServiceAlerts).not.toHaveBeenCalled();
  });
});
