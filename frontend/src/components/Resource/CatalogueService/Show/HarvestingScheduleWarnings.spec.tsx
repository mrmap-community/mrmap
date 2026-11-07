import { useRecordContext } from "react-admin";

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import useServiceAlerts from "../../ServiceAlert/useServiceAlerts";
import HarvestingScheduleWarnings from "./HarvestingScheduleWarnings";

// the translate hook, spied so a test can see which key a warning is answered by
const translate = vi.hoisted(() =>
  vi.fn((key: string) => key.split(".").pop() as string),
);

vi.mock("react-admin", () => ({
  useRecordContext: vi.fn(),
  useTranslate: () => translate,
}));
vi.mock("../../ServiceAlert/useServiceAlerts", () => ({
  default: vi.fn(() => ({ data: [] })),
}));

beforeEach(() => {
  translate.mockClear();
  vi.mocked(useRecordContext, { partial: true }).mockReturnValue({
    id: "csw-1",
  });
  vi.mocked(useServiceAlerts).mockReturnValue(
    { data: [] } as unknown as ReturnType<typeof useServiceAlerts>,
  );
});

describe("harvesting schedule warnings", () => {
  it("asks the alerts of the shown catalogue about its schedules which did not keep their time", () => {
    render(<HarvestingScheduleWarnings />);
    expect(useServiceAlerts).toHaveBeenCalledWith({
      service: "csw-1",
      // the schedule which fires too often and the schedule which did not
      // fire when its crontab said - one request, comma separated (#1086)
      category: "harvest_overdue,harvest_schedule_too_tight",
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

  it("names an overdue schedule by the translation of its state", () => {
    // the message of an overdue alert is the name of its category, so the
    // warning answers the translated state and never the raw key (#1086)
    vi.mocked(useServiceAlerts).mockReturnValue({
      data: [
        {
          id: "harvest_overdue:CatalogueService:7",
          category: "harvest_overdue",
          message: "harvest_overdue",
        },
      ],
    } as unknown as ReturnType<typeof useServiceAlerts>);
    render(<HarvestingScheduleWarnings />);
    expect(screen.getByText("harvest_overdue")).toBeInTheDocument();
    expect(translate).toHaveBeenCalledWith(
      "serviceAlerts.categories.harvest_overdue",
    );
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
