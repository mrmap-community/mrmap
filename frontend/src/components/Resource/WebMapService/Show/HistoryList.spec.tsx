import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useGetList } from "react-admin";
import HistoryList from "./HistoryList";

vi.mock("react-admin", () => ({
  Loading: () => <div>Loading history</div>,
  useGetList: vi.fn(),
  useRecordContext: (record: unknown) => record,
  useTranslate: () => (key: string) => key,
}));

const layer = {
  id: 1,
  historyType: "updated",
  historyDate: "2026-09-18T11:46:40Z",
  historyRelation: { id: "layer-id" },
  delta: [{ field: "title", old: "Old title", new: "New title" }],
};
const service = {
  id: 1,
  historyType: "created",
  historyDate: "2026-08-14T13:24:02Z",
  historyRelation: { id: "service-id" },
};

const layerData = [layer];
const serviceData = [service];

beforeEach(() => {
  vi.mocked(useGetList).mockReset();
  vi.mocked(useGetList, { partial: true }).mockImplementation((resource) => ({
    data: resource === "HistoricalLayer" ? layerData : serviceData,
    isLoading: false,
  }));
});

describe("HistoryList", () => {
  it("orders events newest first and clears selection when changing resource filters", () => {
    render(
      <HistoryList record={{ id: "service-id" }} related="WebMapService" />,
    );
    const eventButtons = screen.getAllByRole("button", {
      name: /^(Layer|WebMapService) /,
    });
    expect(eventButtons[0]).toHaveAccessibleName(/^Layer/);
    fireEvent.click(eventButtons[0]);
    expect(screen.getByText("New title")).toBeInTheDocument();
    fireEvent.mouseDown(
      screen.getByRole("combobox", { name: "Filter history by resource" }),
    );
    fireEvent.click(
      screen.getByRole("option", { name: "Service changes (1)" }),
    );
    expect(screen.queryByText("New title")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Layer / }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^WebMapService / }),
    ).toBeInTheDocument();
  });

  it("clears selection when navigating to a different service", () => {
    const { rerender } = render(
      <HistoryList record={{ id: "service-id" }} related="WebMapService" />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Layer / }));
    rerender(
      <HistoryList
        record={{ id: "another-service" }}
        related="WebMapService"
      />,
    );
    expect(
      screen.queryByRole("region", { name: "Selected event details" }),
    ).not.toBeInTheDocument();
  });

  it("shows fetch errors instead of claiming history is empty", () => {
    vi.mocked(useGetList, { partial: true }).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Offline"),
    });
    render(
      <HistoryList record={{ id: "service-id" }} related="WebMapService" />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Unable to load history.",
    );
  });
});
