import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import HistoryTimeline, { type TimelineRecord } from "./HistoryTimeline";

const events: TimelineRecord[] = [
  {
    id: 1,
    _type: "Layer",
    historyType: "updated",
    historyDate: "2026-09-18T11:46:40Z",
    historyRelation: { id: "layer-12345678" },
    historyUser: { username: "jonas" },
    delta: [{ field: "title", old: null, new: "New layer title" }],
  },
  {
    id: 1,
    _type: "WebMapService",
    historyType: "created",
    historyDate: "2026-08-14T13:24:02Z",
    historyRelation: { id: "service-12345678" },
  },
  {
    id: 2,
    _type: "Layer",
    historyType: "deleted",
    historyDate: "2026-08-13T13:24:02Z",
    historyRelation: { id: "deleted-layer" },
  },
];
const eventButton = (name: string) =>
  screen.getByRole("button", { name: new RegExp(`^${name}`) });

describe("HistoryTimeline", () => {
  it("starts compact and shows only the selected event, even when resource IDs overlap", () => {
    render(<HistoryTimeline events={events} />);
    expect(
      screen.queryByRole("region", { name: "Selected event details" }),
    ).not.toBeInTheDocument();
    fireEvent.click(eventButton("Layer layer"));
    const details = screen.getByRole("region", {
      name: "Selected event details",
    });
    expect(within(details).getByText("New layer title")).toBeInTheDocument();
    expect(within(details).getByText("—")).toBeInTheDocument();
    expect(details).toHaveTextContent("by jonas");
    fireEvent.click(eventButton("WebMapService"));
    expect(
      screen.getAllByRole("region", { name: "Selected event details" }),
    ).toHaveLength(1);
    expect(screen.queryByText("New layer title")).not.toBeInTheDocument();
    expect(
      screen.getByText("No field changes are available for this event."),
    ).toBeInTheDocument();
    fireEvent.click(eventButton("WebMapService"));
    expect(
      screen.queryByRole("region", { name: "Selected event details" }),
    ).not.toBeInTheDocument();
  });

  it("closes deletion details and restores focus to the selected event", () => {
    render(<HistoryTimeline events={events} />);
    const button = eventButton("Layer deleted");
    fireEvent.click(button);
    fireEvent.click(
      screen.getByRole("button", { name: "Close event details" }),
    );
    expect(button).toHaveFocus();
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("scrolls the timeline in both directions using its own width", () => {
    render(<HistoryTimeline events={events} />);
    const region = screen.getByRole("region", {
      name: "History timeline, newest first",
    });
    const scrollBy = vi.fn();
    Object.defineProperty(region, "clientWidth", { value: 500 });
    Object.defineProperty(region, "scrollBy", { value: scrollBy });
    fireEvent.click(
      screen.getByRole("button", { name: "Scroll to older changes" }),
    );
    expect(scrollBy).toHaveBeenLastCalledWith({
      left: 400,
      behavior: "smooth",
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Scroll to newer changes" }),
    );
    expect(scrollBy).toHaveBeenLastCalledWith({
      left: -400,
      behavior: "smooth",
    });
  });

  it("handles empty history and removes details when the selected record disappears", () => {
    const { rerender } = render(<HistoryTimeline events={events} />);
    fireEvent.click(eventButton("Layer layer"));
    rerender(<HistoryTimeline events={[]} />);
    expect(screen.getByText("No changes to display.")).toBeInTheDocument();
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});
