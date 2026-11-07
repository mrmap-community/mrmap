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
  it("asks the alerts of the shown catalogue by state", () => {
    // the api answers one exact category per request, so the two states of a
    // schedule are asked for by themselves instead of filtered locally
    render(<HarvestingScheduleWarnings />);
    expect(useServiceAlerts).toHaveBeenCalledWith({
      service: "csw-1",
      category: "harvest_schedule_too_tight",
    });
    expect(useServiceAlerts).toHaveBeenCalledWith({
      service: "csw-1",
      category: "harvest_overdue",
    });
  });

  it("names the schedule and the harvest which is tighter than it", () => {
    vi.mocked(useServiceAlerts).mockImplementation(
      (filter?: Record<string, string | number | undefined>) =>
        ({
          data:
            filter?.category === "harvest_schedule_too_tight"
              ? [
                  {
                    id: "harvest_schedule_too_tight:CatalogueService:7",
                    category: "harvest_schedule_too_tight",
                    severity: "warning",
                    message:
                      'The schedule "*/5 * * * *" harvests this catalogue more often ' +
                      "than a harvest of it takes: the harvests which finished measured " +
                      "0:40:00 on average.",
                  },
                ]
              : [],
        }) as unknown as ReturnType<typeof useServiceAlerts>,
    );
    render(<HarvestingScheduleWarnings />);
    expect(screen.getByText(/0:40:00/)).toBeInTheDocument();
  });

  it("names the schedule which did not fire when it was expected", () => {
    // the alert of an overdue harvest was answered by the api and shown nowhere
    // on the schedules of the catalogue (#1082)
    vi.mocked(useServiceAlerts).mockImplementation(
      (filter?: Record<string, string | number | undefined>) =>
        ({
          data:
            filter?.category === "harvest_overdue"
              ? [
                  {
                    id: "harvest_overdue:CatalogueService:7",
                    category: "harvest_overdue",
                    severity: "warning",
                    message: "The harvest of this catalogue was expected a night ago.",
                  },
                ]
              : [],
        }) as unknown as ReturnType<typeof useServiceAlerts>,
    );
    render(<HarvestingScheduleWarnings />);
    expect(screen.getByText(/a night ago/)).toBeInTheDocument();
  });

  it("leaves the states of another setting to the screens which own them", () => {
    // an alert of another state answers nothing in these two requests
    const { container } = render(<HarvestingScheduleWarnings />);
    expect(container).toBeEmptyDOMElement();
  });

  it("answers nothing while every schedule kept its time", () => {
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
