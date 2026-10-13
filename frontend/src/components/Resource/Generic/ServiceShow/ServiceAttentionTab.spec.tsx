import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useRecordContext } from "react-admin";
import ServiceAttentionTab from "./ServiceAttentionTab";

vi.mock("react-admin", () => ({
  DateField: ({ source }: { source: string }) => <span>{source}</span>,
  useRecordContext: vi.fn(),
  useRefresh: () => () => undefined,
  useTranslate: () => (key: string) => key.split(".").pop() ?? key,
}));

beforeEach(() => {
  vi.mocked(useRecordContext, { partial: true }).mockReturnValue(undefined);
});

const renderTabWith = (record: Record<string, unknown>) => {
  vi.mocked(useRecordContext, { partial: true }).mockReturnValue(record);
  render(<ServiceAttentionTab />);
};

describe("attention of a service", () => {
  it("asks for nothing when the service needs nothing to do", () => {
    renderTabWith({ id: "wms-1", hasAlert: false });
    expect(screen.getByText("none")).toBeInTheDocument();
    expect(screen.queryByText("monitoringFailed")).not.toBeInTheDocument();
  });

  it("lists the state which needs attention with the time it appeared at", () => {
    renderTabWith({
      id: "wms-1",
      hasAlert: true,
      monitoringFailed: true,
      monitoringFailedAt: "2026-10-13T10:00:00Z",
    });
    expect(screen.getByText("monitoringFailed")).toBeInTheDocument();
    expect(screen.getByText("monitoringFailedAt")).toBeInTheDocument();
    expect(screen.queryByText("updateFailed")).not.toBeInTheDocument();
  });

  it("lists the errors of a service before its warnings", () => {
    renderTabWith({
      id: "wms-1",
      hasAlert: true,
      updateReviewRequired: true,
      updateReviewRequiredAt: "2026-10-13T11:00:00Z",
      monitoringFailed: true,
      monitoringFailedAt: "2026-10-13T10:00:00Z",
    });
    const alerts = screen.getAllByRole("alert");
    expect(alerts.map((alert) => alert.textContent)).toEqual([
      expect.stringContaining("monitoringFailed"),
      expect.stringContaining("updateReviewRequired"),
    ]);
  });

  it("lists the state of the harvesting of a catalogue", () => {
    renderTabWith({
      id: "csw-1",
      hasAlert: true,
      harvestIncomplete: true,
      harvestFailedAt: "2026-10-13T09:00:00Z",
    });
    expect(screen.getByText("harvestIncomplete")).toBeInTheDocument();
    expect(screen.getByText("harvestFailedAt")).toBeInTheDocument();
  });

  it("asks for a state which has no time to answer", () => {
    renderTabWith({ id: "wms-1", hasAlert: true, updateFailed: true });
    expect(screen.getByText("updateFailed")).toBeInTheDocument();
    expect(screen.queryByText("at")).not.toBeInTheDocument();
  });
});
