import { AdminContext, testDataProvider } from "react-admin";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ShowWebFeatureServiceMonitoringRun from "./ShowWebFeatureServiceMonitoringRun";

import "@testing-library/jest-dom/vitest";

vi.mock("./MonitoringProbeResults", () => ({
  default: ({
    groups,
  }: {
    groups: { resource: string; type: string; ids: string[] }[];
  }) => (
    <div>
      {groups.map((group) => (
        <span key={group.resource}>
          {group.resource}:{group.type}:{group.ids.join(",")}
        </span>
      ))}
    </div>
  ),
}));

describe("wfs monitoring run details", () => {
  it("maps the results of a run to the probe results of the wfs", async () => {
    const getOne = vi.fn().mockResolvedValue({
      data: {
        id: "run-1",
        success: true,
        dateCreated: "2026-09-30T12:00:00Z",
        dateDone: "2026-09-30T12:00:12Z",
        getCapabilitiesProbeResults: [{ id: "c1" }],
        getFeatureProbeResults: [{ id: "f1" }, { id: "f2" }],
        setting: null,
      },
    });
    render(
      <AdminContext dataProvider={testDataProvider({ getOne })}>
        <ShowWebFeatureServiceMonitoringRun
          resource="WebFeatureServiceMonitoringRun"
          id="run-1"
        />
      </AdminContext>,
    );
    expect(
      await screen.findByText(
        "WebFeatureServiceGetCapabilitiesProbeResult:GetCapabilities:c1",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "WebFeatureServiceGetFeatureProbeResult:GetFeature:f1,f2",
      ),
    ).toBeInTheDocument();
  });
});
