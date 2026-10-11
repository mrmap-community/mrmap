import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { AdminContext, testDataProvider } from "react-admin";
import { describe, expect, it, vi } from "vitest";

import ShowWebMapServiceMonitoringRun from "./ShowWebMapServiceMonitoringRun";

vi.mock("./MonitoringProbeResults", () => ({
  default: ({
    capabilitiesIds,
    mapIds,
  }: {
    capabilitiesIds: string[];
    mapIds: string[];
  }) => (
    <div>
      <span>{capabilitiesIds.length}</span>
      <span>{mapIds.length}</span>
      <span>Capabilities: {capabilitiesIds.join(",")}</span>
      <span>Maps: {mapIds.join(",")}</span>
    </div>
  ),
}));

describe("monitoring run details", () => {
  it.each([
    { success: true, dateDone: "2026-09-30T12:00:12Z", status: "passed" },
    { success: false, dateDone: "2026-09-30T12:00:12Z", status: "failed" },
    { success: false, dateDone: null, status: "running" },
  ])(
    "shows $status status with timing and result counts",
    async ({ success, dateDone, status }) => {
      const getOne = vi.fn().mockResolvedValue({
        data: {
          id: "run-1",
          success,
          dateDone,
          dateCreated: "2026-09-30T12:00:00Z",
          getCapabilititesProbeResults: [{ id: "c1" }, { id: "c2" }],
          getMapProbeResults: [{ id: "m1" }, { id: "m2" }, { id: "m3" }],
          setting: null,
        },
      });
      render(
        <AdminContext dataProvider={testDataProvider({ getOne })}>
          <ShowWebMapServiceMonitoringRun
            resource="WebMapServiceMonitoringRun"
            id="run-1"
          />
        </AdminContext>,
      );
      expect(await screen.findByRole("alert")).toHaveTextContent(
        `monitoringRun.${status}Message`,
      );
      expect(screen.getByText("2")).toBeInTheDocument();
      expect(screen.getByText("3")).toBeInTheDocument();
      expect(
        screen.getByText("monitoringRun.settingUnavailable"),
      ).toBeInTheDocument();
      if (dateDone) expect(screen.getByText("12.00 s")).toBeInTheDocument();
      else expect(screen.queryByText("12.00 s")).not.toBeInTheDocument();
    },
  );
  it("loads the selected run and scopes both result lists to it", async () => {
    const getOne = vi.fn().mockResolvedValue({
      data: {
        id: "run-1",
        success: true,
        dateCreated: "2026-09-30T12:00:00Z",
        dateDone: "2026-09-30T12:00:12Z",
        getCapabilititesProbeResults: [{ id: "c1" }],
        getMapProbeResults: [{ id: "m1" }],
      },
    });
    render(
      <AdminContext dataProvider={testDataProvider({ getOne })}>
        <ShowWebMapServiceMonitoringRun
          resource="WebMapServiceMonitoringRun"
          id="run-1"
        />
      </AdminContext>,
    );
    expect(await screen.findByText("Capabilities: c1")).toBeInTheDocument();
    expect(screen.getByText("Maps: m1")).toBeInTheDocument();
    expect(getOne).toHaveBeenCalledWith(
      "WebMapServiceMonitoringRun",
      expect.objectContaining({ id: "run-1" }),
    );
  });
});
